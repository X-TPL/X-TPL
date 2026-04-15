import subprocess
import yaml
import pathlib
import threading
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
DOCKERFILE_DIR = ROOT
GLOBAL_LOG = OUTPUT_DIR / "build.log"
IMAGE_PREFIX = "react-android"
BUILD_LOCKS = {}  # (node_version , jdk_version) -> Lock
GLOBAL_LOCK = threading.Lock()



# ---------- helpers ----------


def run(cmd, log_file: pathlib.Path, check=True):
    with log_file.open("a") as f:
        f.write("\n> " + " ".join(cmd) + "\n")

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=7200
            )
        except subprocess.TimeoutExpired as e:
            f.write("\nERROR: Command timed out\n")
            raise

        f.write(result.stdout)

        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd)



def load_manifest():
    with open(ROOT / "build_manifest.yaml") as f:
        return yaml.safe_load(f)["apps"]

def pick_next_node_version(node):
    node = str(node)
    if node == "16": return "18"
    elif node == "18": return "20"
    elif node == "20": return "22"
    return None


# ---------- docker image handling ----------

def image_tag(node_version: str, jdk_version: int) -> str:
    return f"{IMAGE_PREFIX}:{node_version}-jdk{jdk_version}"


def image_exists(tag: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def ensure_image(node_version: str, jdk_version: str):
    tag = image_tag(node_version, jdk_version)

    if image_exists(tag):
        return

    # one lock per node+jdk combo
    key = (node_version, jdk_version)

    with GLOBAL_LOCK:
        lock = BUILD_LOCKS.setdefault(key, threading.Lock())

    with lock:
        if image_exists(tag):
            return

        print(f"[image] building {tag}")
        run([
            "docker", "build",
            "--build-arg", f"NODE_VERSION={node_version}",
            "--build-arg", f"JDK_VERSION={jdk_version}",
            "-t", tag,
            str(DOCKERFILE_DIR),
        ], GLOBAL_LOG, check=True)
        if not image_exists(tag):
            raise RuntimeError(f"Image build failed for {tag}")


# ---------- build execution ----------

def build_app(app):
    app_id = app["id"]
    node_version = str(app["node"])
    output_type = app.get("output", "apk")
    app_path = ROOT / app["path"]

    out_dir = OUTPUT_DIR / app_id
    out_dir.mkdir(parents=True, exist_ok=True)
    r8_dir = out_dir / "r8"
    r8_dir.mkdir(parents=True, exist_ok=True)

    log_file = out_dir / "build.log"
    log_file.write_text("")
    jdk_version = app["jdk"]
    while node_version:
        try:
            run(
                ["echo", f"Attempting build for {app_id} with Node {node_version} and jdk {jdk_version}"],
                log_file,
                check=False
            )

            ensure_image(node_version, jdk_version)

            run([
                "docker", "run", "--rm",
                "-v", f"{app_path}:/app",
                "-v", f"{out_dir}:/output",
                "-v", f"{pathlib.Path.home()}/.npm:/root/.npm",
                image_tag(node_version, jdk_version),
                "bash", "-c",
                f"""
                set -e

                cd /app && \

                # ---- install deps (yarn or npm) ----
                if [ -f yarn.lock ]; then
                    yarn install --ignore-scripts;
                else
                    npm install --ignore-scripts;
                fi && \

                # ---- detect expo ----
                if grep -q '"expo"' package.json; then
                    echo "Expo project detected";
                    CI=1 npx expo prebuild --platform android
                fi && \

                cd android && \
                
                chmod +x gradlew && \
                
                # ---- clean gradle ----
                (./gradlew clean || true) && \

                # ---- enable ABI splits ----
                if grep -q 'splits' app/build.gradle 2>/dev/null; then \
                    sed -i 's/enable false/enable true/' app/build.gradle || true; \
                else \
                    sed -i '/^android[[:space:]]*{{/a\    splits {{\\n        abi {{\\n            reset()\\n            enable true\\n            universalApk false\\n            include "armeabi-v7a", "arm64-v8a", "x86", "x86_64"\\n        }}\\n    }}' app/build.gradle || true; \
                fi && \

                # ---- build debug apk ----
                ./gradlew assembleDebug --no-daemon || exit 1 && \

                APK_PATH="app/build/outputs/apk/debug"

                if ! ls $APK_PATH/*.apk 1> /dev/null 2>&1; then
                    echo "ERROR: APK not generated"
                    exit 1
                fi
                # ---- copy output ----
                cp app/build/outputs/apk/debug/*.apk /output/

                # ---- copy TPL metadata ----
                [ -f ../package.json ] && cp ../package.json /output/ || true
                [ -f ../package-lock.json ] && cp ../package-lock.json /output/ || true
                [ -f ../yarn.lock ] && cp ../yarn.lock /output/ || true
                """
            ], log_file)

            run([
                "docker", "run", "--rm",
                "-v", f"{app_path}:/app",
                "-v", f"{out_dir}:/output",
                "-v", f"{pathlib.Path.home()}/.npm:/root/.npm",
                image_tag(node_version, jdk_version),
                "bash", "-c",
                f"""
                set -e

                cd /app && \

                # ---- install deps (yarn or npm) ----
                if [ -f yarn.lock ]; then
                    yarn install --ignore-scripts;
                else
                    npm install --ignore-scripts;
                fi && \

                # ---- stub missing parent package.json (monorepo metro configs) ----
                [ ! -f ../package.json ] && cp package.json ../package.json 2>/dev/null || true && \

                # ---- patch toReversed (Node <20 compat) ----
                find node_modules -name "loadConfig.js" -path "*/metro-config/*" -exec sed -i 's/\.toReversed()/.slice().reverse()/g' {{}} \; 2>/dev/null || true && \

                # ---- patch ESM-only metro config deps ----
                if grep -q 'react-native-monorepo-config' metro.config.js 2>/dev/null; then \
                    if [ -d node_modules/@react-native/metro-config ]; then \
                        printf 'const {{getDefaultConfig, mergeConfig}} = require("@react-native/metro-config");\nmodule.exports = mergeConfig(getDefaultConfig(__dirname), {{}});\n' > metro.config.js; \
                    else \
                        printf 'const {{getDefaultConfig}} = require("metro-config");\nmodule.exports = getDefaultConfig(__dirname);\n' > metro.config.js; \
                    fi; \
                fi && \

                # ---- detect expo ----
                if grep -q '"expo"' package.json; then
                    echo "Expo project detected";
                    CI=1 npx expo prebuild --platform android
                fi && \

                cd android && \

                chmod +x gradlew && \

                # ---- enable ABI splits ----
                if grep -q 'splits' app/build.gradle 2>/dev/null; then \
                    sed -i 's/enable false/enable true/' app/build.gradle || true; \
                else \
                    sed -i '/^android[[:space:]]*{{/a\    splits {{\\n        abi {{\\n            reset()\\n            enable true\\n            universalApk false\\n            include "armeabi-v7a", "arm64-v8a", "x86", "x86_64"\\n        }}\\n    }}' app/build.gradle || true; \
                fi && \

                # ---- enable R8 ----
                sed -i 's/enableProguardInReleaseBuilds = false/enableProguardInReleaseBuilds = true/' app/build.gradle || true && \

                # ---- sign release with debug key ----
                sed -i '/buildTypes/,/}}/s/release {{/release {{\n            signingConfig signingConfigs.debug/' app/build.gradle || true && \

                # ---- build release apk ----
                ./gradlew assembleRelease --no-daemon || exit 1 && \
                    
                APK_PATH="app/build/outputs/apk/release"

                if ! ls $APK_PATH/*.apk 1> /dev/null 2>&1; then
                    echo "ERROR: APK not generated"
                    exit 1
                fi

                # ---- copy output ----
                cp app/build/outputs/apk/release/*.apk /output/r8/

                # ---- copy TPL metadata ----
                [ -f ../package.json ] && cp ../package.json /output/r8/ || true
                [ -f ../package-lock.json ] && cp ../package-lock.json /output/r8/ || true
                [ -f ../yarn.lock ] && cp ../yarn.lock /output/r8/ || true
                """
            ], log_file)

            run(
                ["echo", f"Build succeeded with Node {node_version}"],
                log_file,
                check=False
            )

            print(f"[done] {app_id} ({node_version})")
            return

        except Exception as e:
            run(
                ["echo", f"Build failed with Node {node_version} and jdk version {jdk_version} with the following error: {e}"],
                log_file,
                check=False
            )
        node_version = pick_next_node_version(node_version)




# ---------- main ----------

def main():
    apps = load_manifest()
    OUTPUT_DIR.mkdir(exist_ok=True)

    max_parallel = max(1, (os.cpu_count() or 2) // 2)
    futures = []
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        for app in apps:
            futures.append(pool.submit(build_app, app))

        for future in as_completed(futures):
            try:
                future.result()  # raises exception if build_app failed
            except Exception as e:
                print(f"[executor error] {e}")


if __name__ == "__main__":
    main()
