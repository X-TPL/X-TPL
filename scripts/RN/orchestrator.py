import pathlib
import threading
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from scripts.common.helpers import run, load_manifest, image_exists, run_builds  # noqa: F401

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
DOCKERFILE_DIR = ROOT
GLOBAL_LOG = OUTPUT_DIR / "build.log"
IMAGE_PREFIX = "react-android"
BUILD_LOCKS = {}  # (node_version, jdk_version) -> Lock
GLOBAL_LOCK = threading.Lock()

def pick_next_node_version(node):
    node = str(node)
    if node == "16": return "18"
    elif node == "18": return "20"
    elif node == "20": return "22"
    return None


# ---------- docker image handling ----------

def image_tag(node_version: str, jdk_version: int) -> str:
    return f"{IMAGE_PREFIX}:{node_version}-jdk{jdk_version}"


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
                "-v", f"{app_path}:/source:ro",
                "-v", f"{out_dir}:/output",
                "-v", f"{pathlib.Path.home()}/.npm:/root/.npm",
                image_tag(node_version, jdk_version),
                "bash", "-c",
                f"""
                set -e

                cp -r /source/. /app && \
                cd /app && \

                # ---- install deps (yarn or npm) ----
                if [ -f yarn.lock ]; then
                    yarn install;
                else
                    npm install --ignore-scripts;
                fi && \

                # ---- stub missing google-services.json (Firebase/Expo prebuild) ----
                if [ ! -f google-services.json ]; then \
                    python3 -c "import json; open('google-services.json','w').write(json.dumps({{'project_info':{{'project_number':'000000000000','project_id':'stub','storage_bucket':'stub.appspot.com'}},'client':[{{'client_info':{{'mobilesdk_app_id':'1:000000000000:android:0000000000000000','android_client_info':{{'package_name':'com.stub'}}}},'oauth_client':[],'api_key':[{{'current_key':'stub'}}],'services':{{'appinvite_service':{{'other_platform_oauth_client':[]}}}}}}],'configuration_version':'1'}}))" 2>/dev/null || true; \
                fi && \

                # ---- detect expo ----
                if grep -q '"expo"' package.json && [ ! -d android ]; then
                    echo "Expo project detected";
                    CI=1 npx expo prebuild --platform android
                fi && \

                export PATH="/app/node_modules/.bin:$PATH" && \
                cd android && \

                chmod +x gradlew && \

                # ---- patch settings.gradle to use local react-native CLI (avoids npx failures) ----
                sed -i 's/autolinkLibrariesWithCommand()/autolinkLibrariesWithCommand("node node_modules\/.bin\/react-native config")/' settings.gradle 2>/dev/null || true && \

                # ---- clean gradle ----
                (./gradlew clean || true) && \

                # ---- pre-resolve AAR transforms so CMake finds prefab paths ----
                ./gradlew :app:dependencies --configuration debugCompileClasspath --no-daemon > /dev/null 2>&1 || true && \

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
                "-v", f"{app_path}:/source:ro",
                "-v", f"{out_dir}:/output",
                "-v", f"{pathlib.Path.home()}/.npm:/root/.npm",
                image_tag(node_version, jdk_version),
                "bash", "-c",
                f"""
                set -e

                cp -r /source/. /app && \
                cd /app && \

                # ---- install deps (yarn or npm) ----
                if [ -f yarn.lock ]; then
                    yarn install;
                else
                    npm install --ignore-scripts;
                fi && \

                # ---- stub missing parent package.json (monorepo metro configs) ----
                [ ! -f ../package.json ] && cp package.json ../package.json 2>/dev/null || true && \

                # ---- patch toReversed (Node <20 compat) ----
                find node_modules -name "loadConfig.js" -path "*/metro-config/*" -exec sed -i 's/\.toReversed()/.slice().reverse()/g' {{}} \; 2>/dev/null || true && \

                # ---- patch missing expo/AppEntry ----
                if grep -q '"main".*expo/AppEntry' package.json 2>/dev/null && \
                   [ ! -f node_modules/expo/AppEntry.js ] && [ ! -f node_modules/expo/AppEntry.ts ]; then \
                    node -e "const fs=require('fs'); const p=JSON.parse(fs.readFileSync('package.json','utf8')); if(fs.existsSync('index.js')){{p.main='index.js'; fs.writeFileSync('package.json',JSON.stringify(p,null,2));}}" 2>/dev/null || true; \
                fi && \

                # ---- patch broken metro config (ESM-only or null-returning) ----
                if grep -q 'react-native-monorepo-config' metro.config.js 2>/dev/null || \
                   ! node -e "const c=require('./metro.config.js'); if(!c||typeof c!=='object') process.exit(1);" 2>/dev/null; then \
                    if [ -d node_modules/@react-native/metro-config ]; then \
                        printf 'const {{getDefaultConfig, mergeConfig}} = require("@react-native/metro-config");\nmodule.exports = mergeConfig(getDefaultConfig(__dirname), {{}});\n' > metro.config.js; \
                    else \
                        printf 'const {{getDefaultConfig}} = require("metro-config");\nmodule.exports = getDefaultConfig(__dirname);\n' > metro.config.js; \
                    fi; \
                fi && \

                # ---- stub missing google-services.json (Firebase/Expo prebuild) ----
                if [ ! -f google-services.json ]; then \
                    python3 -c "import json; open('google-services.json','w').write(json.dumps({{'project_info':{{'project_number':'000000000000','project_id':'stub','storage_bucket':'stub.appspot.com'}},'client':[{{'client_info':{{'mobilesdk_app_id':'1:000000000000:android:0000000000000000','android_client_info':{{'package_name':'com.stub'}}}},'oauth_client':[],'api_key':[{{'current_key':'stub'}}],'services':{{'appinvite_service':{{'other_platform_oauth_client':[]}}}}}}],'configuration_version':'1'}}))" 2>/dev/null || true; \
                fi && \

                # ---- detect expo ----
                if grep -q '"expo"' package.json && [ ! -d android ]; then
                    echo "Expo project detected";
                    CI=1 npx expo prebuild --platform android
                fi && \

                # ---- stub missing metro watchFolders paths ----
                mkdir -p /src 2>/dev/null || true && \

                # ---- ensure TypeScript babel support (fixes 'interface' SyntaxError in metro bundling) ----
                if [ -d node_modules/babel-preset-expo ]; then \
                    grep -ql "expo\|typescript" babel.config.js .babelrc .babelrc.js babel.config.json 2>/dev/null || \
                    printf 'module.exports=function(api){{api.cache(true);return{{presets:["babel-preset-expo"]}};}};\n' > babel.config.js; \
                fi && \

                export PATH="/app/node_modules/.bin:$PATH" && \
                cd android && \

                chmod +x gradlew && \

                # ---- patch settings.gradle to use local react-native CLI (avoids npx failures) ----
                sed -i 's/autolinkLibrariesWithCommand()/autolinkLibrariesWithCommand("node node_modules\/.bin\/react-native config")/' settings.gradle 2>/dev/null || true && \

                # ---- disable Sentry source map upload (no credentials in CI) ----
                export SENTRY_DISABLE_AUTO_UPLOAD=true && \
                echo "sentryUploadEnabled=false" >> gradle.properties 2>/dev/null || true && \

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

                # ---- pre-resolve AAR transforms so CMake finds prefab paths ----
                ./gradlew :app:dependencies --configuration releaseCompileClasspath --no-daemon > /dev/null 2>&1 || true && \

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
    apps = load_manifest(ROOT)
    run_builds(build_app, apps, OUTPUT_DIR)


if __name__ == "__main__":
    main()
