import pathlib
import threading
import time
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from scripts.common.helpers import run, load_manifest, image_exists, record_build, run_builds

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
DOCKERFILE_DIR = ROOT
GLOBAL_LOG = OUTPUT_DIR / "build.log"
IMAGE_PREFIX = "cordova-android"
BUILD_LOCKS = {}  # (node_version , jdk_version) -> Lock
GLOBAL_LOCK = threading.Lock()


def pick_next_jdk_version(jdk):
    if jdk == 8: return 11
    elif jdk == 11: return 17
    return None


# ---------- docker image handling ----------

def image_tag(node_version: str, jdk_version: int) -> str:
    return f"{IMAGE_PREFIX}:{node_version}-jdk{jdk_version}"


def ensure_image(node_version: str, jdk_version: str):
    tag = image_tag(node_version, jdk_version)
    if image_exists(tag):
        return

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
    node_version = 20 #app["node"]
    app_path = ROOT / app["path"]
    jdk_version = app["jdk"]

    out_dir = OUTPUT_DIR / app_id
    out_dir.mkdir(parents=True, exist_ok=True)
    r8_dir = out_dir / "r8"
    r8_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "build.log"
    log_file.write_text("")

    while jdk_version:
        try:
            run(
                ["echo", f"Attempting build for {app_id} with Node {node_version} and JDK {jdk_version}"],
                log_file,
                check=False
            )

            ensure_image(node_version, jdk_version)
            bash_script = r"""set -e
            cp -r /source/. /app
            cd /app
            rm -rf platforms plugins node_modules || true
            rm -rf $GRADLE_USER_HOME || true
            mkdir -p $GRADLE_USER_HOME
            echo "systemProp.socksProxyHost=172.17.0.1" >> $GRADLE_USER_HOME/gradle.properties
            echo "systemProp.socksProxyPort=9050" >> $GRADLE_USER_HOME/gradle.properties

            # unset Gradle options
            unset JAVA_OPTS

            # install deps
            if [ -f yarn.lock ]; then
                yarn install --ignore-scripts
            else
                npm install --ignore-scripts
            fi

            # ensure android platform
            cordova platform add android
            cordova prepare android

            # ---- PATCH ROOT GRADLE FILES (CRITICAL FIX) ----
            for f in platforms/android/build.gradle platforms/android/CordovaLib/build.gradle; do
                if [ -f "$f" ]; then
                    # add missing repositories to buildscript + allprojects
                    sed -i '/buildscript[[:space:]]*{/a\
                repositories {\
                    google()\
                    mavenCentral()\
                    maven { url "https://plugins.gradle.org/m2/" }\
                    maven { url "https://maven.aliyun.com/repository/public" }\
                    maven { url "https://jcenter.bintray.com/" }\
                    maven { url "https://jitpack.io" }\
                }\
            ' "$f" || true

                    sed -i '/allprojects[[:space:]]*{/a\
                repositories {\
                    google()\
                    mavenCentral()\
                    maven { url "https://plugins.gradle.org/m2/" }\
                    maven { url "https://maven.aliyun.com/repository/public" }\
                    maven { url "https://jcenter.bintray.com/" }\
                    maven { url "https://jitpack.io" }\
                }\
            ' "$f" || true
                fi
            done

            # ---- FIX versioncompare (very common failure) ----
            grep -RIl 'com.g00fy2:versioncompare:1.3.4' platforms/android 2>/dev/null | \
            xargs -r sed -i 's/com.g00fy2:versioncompare:1.3.4/io.github.g00fy2:versioncompare:1.5.0/g' || true

            # ---- fix versioncompare imports (CRITICAL) ----
            find platforms/android \( -name "*.gradle" -o -name "*.gradle.kts" \) -print0 | \
            xargs -0 sed -i 's/import com\.g00fy2\.versioncompare\.Version/import io.github.g00fy2.versioncompare.Version/g' || true

            # ---- OPTIONAL: remove illegal JVM args ----
            find platforms/android -type f -exec sed -i 's/--illegal-access=permit//g' {} + || true

            # ---- JDK 8 specific patch (minimal, no overwrite!) ----
            if [ \"""" + str(jdk_version) + r"""\" = "8" ]; then
                # ensure older sdk usage (do NOT overwrite build.gradle anymore)
                find platforms/android -name "build.gradle" -exec \
                    sed -i 's/compileSdkVersion [0-9]\+/compileSdkVersion 30/g' {} \; || true

                find platforms/android -name "build.gradle" -exec \
                    sed -i 's/targetSdkVersion [0-9]\+/targetSdkVersion 30/g' {} \; || true
            fi

            # ---- android sdk path ----
            echo "sdk.dir=$ANDROID_HOME" > platforms/android/local.properties

            # ---- force APK output (suppress AAB generation) ----
            echo "android.bundle.enableAll=false" >> platforms/android/gradle.properties

            # ---- enable ABI splits ----
            if grep -q 'splits' platforms/android/app/build.gradle 2>/dev/null; then
                sed -i 's/enable false/enable true/' platforms/android/app/build.gradle || true
            else
                sed -i '/^android[[:space:]]*{/a\    splits {\n        abi {\n            reset()\n            enable true\n            universalApk false\n            include "armeabi-v7a", "arm64-v8a", "x86", "x86_64"\n        }\n    }' platforms/android/app/build.gradle || true
            fi

            # ---- build debug APK ----
            cordova build android --debug --no-interactive --verbose

            cp platforms/android/app/build/outputs/apk/debug/*.apk /output/

            # ---- copy TPL metadata ----
            [ -f config.xml ] && cp config.xml /output/ || true
            [ -f plugins/fetch.json ] && cp plugins/fetch.json /output/ || true
            [ -f plugins/android.json ] && cp plugins/android.json /output/ || true
            [ -f platforms/android/app/build.gradle ] && cp platforms/android/app/build.gradle /output/app-build.gradle || true
            [ -f platforms/android/build.gradle ] && cp platforms/android/build.gradle /output/root-build.gradle || true
            [ -f platforms/android/settings.gradle ] && cp platforms/android/settings.gradle /output/ || true
            [ -f package.json ] && cp package.json /output/ || true
            [ -f package-lock.json ] && cp package-lock.json /output/ || true
            [ -f yarn.lock ] && cp yarn.lock /output/ || true
            [ -f pnpm-lock.yaml ] && cp pnpm-lock.yaml /output/ || true
            mkdir -p /output/plugin_manifests
            find plugins -name "plugin.xml" 2>/dev/null | while read f; do cp "$f" /output/plugin_manifests/$(echo "$f" | tr '/' '_') 2>/dev/null; done || true
            find plugins -name "*.gradle" 2>/dev/null | while read f; do cp "$f" /output/ 2>/dev/null; done || true
            find platforms/android -name "*.gradle" 2>/dev/null | grep -v "/build/" | while read f; do cp "$f" /output/ 2>/dev/null; done || true
            mkdir -p /output/libs
            find plugins platforms/android -name "*.jar" -not -name "gradle-wrapper.jar" 2>/dev/null | grep -v "/build/" | while read f; do cp "$f" /output/libs/ 2>/dev/null; done || true
            find plugins platforms/android -name "*.aar" 2>/dev/null | grep -v "/build/" | while read f; do cp "$f" /output/libs/ 2>/dev/null; done || true
            find plugins platforms/android -name "*.so" 2>/dev/null | grep -v "/build/" | while read f; do cp "$f" /output/libs/ 2>/dev/null; done || true
            """
            _csv = OUTPUT_DIR / "builds.csv"

            _t = time.time()
            _ok = True
            try:
                run([
                    "docker", "run", "--rm",
                    "-v", f"{app_path}:/source:ro",
                    "-v", f"{out_dir}:/output",
                    "-v", f"{pathlib.Path.home()}/.npm:/root/.npm",
                    image_tag(node_version, jdk_version),
                    "bash", "-c", bash_script
                ], log_file)
            except Exception:
                _ok = False
                raise
            finally:
                record_build(_csv, app_id, "debug", _ok, time.time() - _t)

            r8_script = r"""set -e
            cp -r /source/. /app
            cd /app
            rm -rf platforms plugins node_modules || true
            rm -rf $GRADLE_USER_HOME || true
            mkdir -p $GRADLE_USER_HOME
            echo "systemProp.socksProxyHost=172.17.0.1" >> $GRADLE_USER_HOME/gradle.properties
            echo "systemProp.socksProxyPort=9050" >> $GRADLE_USER_HOME/gradle.properties

            # unset Gradle options
            unset JAVA_OPTS

            # install deps
            if [ -f yarn.lock ]; then
                yarn install --ignore-scripts
            else
                npm install --ignore-scripts
            fi

            # ensure android platform
            cordova platform add android
            cordova prepare android

            # ---- PATCH ROOT GRADLE FILES (CRITICAL FIX) ----
            for f in platforms/android/build.gradle platforms/android/CordovaLib/build.gradle; do
                if [ -f "$f" ]; then
                    sed -i '/buildscript[[:space:]]*{/a\
                repositories {\
                    google()\
                    mavenCentral()\
                    maven { url "https://plugins.gradle.org/m2/" }\
                    maven { url "https://maven.aliyun.com/repository/public" }\
                    maven { url "https://jcenter.bintray.com/" }\
                    maven { url "https://jitpack.io" }\
                }\
            ' "$f" || true

                    sed -i '/allprojects[[:space:]]*{/a\
                repositories {\
                    google()\
                    mavenCentral()\
                    maven { url "https://plugins.gradle.org/m2/" }\
                    maven { url "https://maven.aliyun.com/repository/public" }\
                    maven { url "https://jcenter.bintray.com/" }\
                    maven { url "https://jitpack.io" }\
                }\
            ' "$f" || true
                fi
            done

            # ---- FIX versioncompare (very common failure) ----
            grep -RIl 'com.g00fy2:versioncompare:1.3.4' platforms/android 2>/dev/null | \
            xargs -r sed -i 's/com.g00fy2:versioncompare:1.3.4/io.github.g00fy2:versioncompare:1.5.0/g' || true

            # ---- fix versioncompare imports (CRITICAL) ----
            find platforms/android \( -name "*.gradle" -o -name "*.gradle.kts" \) -print0 | \
            xargs -0 sed -i 's/import com\.g00fy2\.versioncompare\.Version/import io.github.g00fy2.versioncompare.Version/g' || true

            # ---- OPTIONAL: remove illegal JVM args ----
            find platforms/android -type f -exec sed -i 's/--illegal-access=permit//g' {} + || true

            # ---- JDK 8 specific patch ----
            if [ \"""" + str(jdk_version) + r"""\" = "8" ]; then
                find platforms/android -name "build.gradle" -exec \
                    sed -i 's/compileSdkVersion [0-9]\+/compileSdkVersion 30/g' {} \; || true

                find platforms/android -name "build.gradle" -exec \
                    sed -i 's/targetSdkVersion [0-9]\+/targetSdkVersion 30/g' {} \; || true
            fi

            # ---- android sdk path ----
            echo "sdk.dir=$ANDROID_HOME" > platforms/android/local.properties

            # ---- force APK output (suppress AAB generation) ----
            echo "android.bundle.enableAll=false" >> platforms/android/gradle.properties

            # ---- enable ABI splits ----
            if grep -q 'splits' platforms/android/app/build.gradle 2>/dev/null; then
                sed -i 's/enable false/enable true/' platforms/android/app/build.gradle || true
            else
                sed -i '/^android[[:space:]]*{/a\    splits {\n        abi {\n            reset()\n            enable true\n            universalApk false\n            include "armeabi-v7a", "arm64-v8a", "x86", "x86_64"\n        }\n    }' platforms/android/app/build.gradle || true
            fi

            # ---- enable R8 / minification ----
            sed -i 's/minifyEnabled false/minifyEnabled true/' platforms/android/app/build.gradle || true

            # ---- sign release with debug key ----
            sed -i '/buildTypes/,/}/s/release {/release {\n            signingConfig signingConfigs.debug/' platforms/android/app/build.gradle || true

            # ---- build release APK ----
            cordova build android --release --no-interactive --verbose

            cp platforms/android/app/build/outputs/apk/release/*.apk /output/r8/

            # ---- copy TPL metadata ----
            [ -f config.xml ] && cp config.xml /output/r8/ || true
            [ -f plugins/fetch.json ] && cp plugins/fetch.json /output/r8/ || true
            [ -f plugins/android.json ] && cp plugins/android.json /output/r8/ || true
            [ -f platforms/android/app/build.gradle ] && cp platforms/android/app/build.gradle /output/r8/app-build.gradle || true
            [ -f platforms/android/build.gradle ] && cp platforms/android/build.gradle /output/r8/root-build.gradle || true
            [ -f platforms/android/settings.gradle ] && cp platforms/android/settings.gradle /output/r8/ || true
            [ -f package.json ] && cp package.json /output/r8/ || true
            [ -f package-lock.json ] && cp package-lock.json /output/r8/ || true
            [ -f yarn.lock ] && cp yarn.lock /output/r8/ || true
            [ -f pnpm-lock.yaml ] && cp pnpm-lock.yaml /output/r8/ || true
            mkdir -p /output/r8/plugin_manifests
            find plugins -name "plugin.xml" 2>/dev/null | while read f; do cp "$f" /output/r8/plugin_manifests/$(echo "$f" | tr '/' '_') 2>/dev/null; done || true
            find plugins -name "*.gradle" 2>/dev/null | while read f; do cp "$f" /output/r8/ 2>/dev/null; done || true
            find platforms/android -name "*.gradle" 2>/dev/null | grep -v "/build/" | while read f; do cp "$f" /output/r8/ 2>/dev/null; done || true
            mkdir -p /output/r8/libs
            find plugins platforms/android -name "*.jar" -not -name "gradle-wrapper.jar" 2>/dev/null | grep -v "/build/" | while read f; do cp "$f" /output/r8/libs/ 2>/dev/null; done || true
            find plugins platforms/android -name "*.aar" 2>/dev/null | grep -v "/build/" | while read f; do cp "$f" /output/r8/libs/ 2>/dev/null; done || true
            find plugins platforms/android -name "*.so" 2>/dev/null | grep -v "/build/" | while read f; do cp "$f" /output/r8/libs/ 2>/dev/null; done || true
            """
            _t = time.time()
            _ok = True
            try:
                run([
                    "docker", "run", "--rm",
                    "-v", f"{app_path}:/source:ro",
                    "-v", f"{out_dir}:/output",
                    "-v", f"{pathlib.Path.home()}/.npm:/root/.npm",
                    image_tag(node_version, jdk_version),
                    "bash", "-c", r8_script
                ], log_file)
            except Exception:
                _ok = False
                raise
            finally:
                record_build(_csv, app_id, "r8", _ok, time.time() - _t)

            run(
                ["echo", f"Build succeeded with Node {node_version} and JDK {jdk_version}"],
                log_file,
                check=False
            )

            print(f"[done] {app_id} ({node_version})")
            return

        except Exception as e:
            run(
                ["echo", f"Build failed with Node {node_version} and JDK {jdk_version}: {e}"],
                log_file,
                check=False
            )

        jdk_version = pick_next_jdk_version(jdk_version)


# ---------- main ----------

def main():
    apps = load_manifest(ROOT)
    run_builds(build_app, apps, OUTPUT_DIR)


if __name__ == "__main__":
    main()
