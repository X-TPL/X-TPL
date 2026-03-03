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


def ensure_image(node_version: str):
    jdk_version = 17
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
    node_version = app["node"]
    output_type = app.get("output", "apk")
    app_path = ROOT / app["path"]

    out_dir = OUTPUT_DIR / app_id
    out_dir.mkdir(parents=True, exist_ok=True)

    log_file = out_dir / "build.log"
    log_file.write_text("")
    jdk_version = 17
    while node_version:
        try:
            run(
                ["echo", f"Attempting build for {app_id} with Node {node_version} and jdk {jdk_version}"],
                log_file,
                check=False
            )

            ensure_image(node_version)

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
                    yarn install; #--frozen-lockfile
                elif [ -f package-lock.json ]; then
                    npm ci;
                else
                    npm install;
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

                # ---- build debug apk ----
                ./gradlew assembleDebug --no-daemon && \

                # ---- copy output ----
                cp app/build/outputs/apk/debug/*.apk /output/
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
