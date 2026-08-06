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
IMAGE_PREFIX = "maui-android"
BUILD_LOCKS = {}  # (dotnet_version, jdk_version) -> Lock
GLOBAL_LOCK = threading.Lock()

DOTNET_VERSIONS = [6, 7, 8, 9]


def next_dotnet_version(current: int):
    try:
        idx = DOTNET_VERSIONS.index(current)
    except ValueError:
        return None
    if idx + 1 < len(DOTNET_VERSIONS):
        return DOTNET_VERSIONS[idx + 1]
    return None


def pick_jdk(dotnet_version: int) -> int:
    return 11 if dotnet_version <= 7 else 17


# ---------- docker image handling ----------

def image_tag(dotnet_version: int, jdk_version: int) -> str:
    return f"{IMAGE_PREFIX}:{dotnet_version}-jdk{jdk_version}"


def ensure_image(dotnet_version: int):
    jdk_version = pick_jdk(dotnet_version)
    tag = image_tag(dotnet_version, jdk_version)

    if image_exists(tag):
        return

    key = (dotnet_version, jdk_version)

    with GLOBAL_LOCK:
        lock = BUILD_LOCKS.setdefault(key, threading.Lock())

    with lock:
        if image_exists(tag):
            return

        print(f"[image] building {tag}")
        run([
            "docker", "build",
            "--build-arg", f"DOTNET_VERSION={dotnet_version}",
            "--build-arg", f"JDK_VERSION={jdk_version}",
            "-t", tag,
            str(DOCKERFILE_DIR),
        ], GLOBAL_LOG, check=True)

        if not image_exists(tag):
            raise RuntimeError(f"Image build failed for {tag}")


# ---------- build execution ----------

def build_app(app):
    attempts = 0
    max_attempts = len(DOTNET_VERSIONS)
    app_id = app["id"]
    dotnet_version = int(app["dotnet"])
    app_path = ROOT / app["path"]
    csproj = app["csproj"]

    out_dir = OUTPUT_DIR / app_id
    out_dir.mkdir(parents=True, exist_ok=True)
    r8_dir = out_dir / "r8"
    r8_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "build.log"
    log_file.write_text("")

    while dotnet_version and attempts < max_attempts:
        attempts += 1
        jdk_version = pick_jdk(dotnet_version)

        try:
            run(
                ["echo", f"Attempting build for {app_id} with .NET {dotnet_version} and JDK {jdk_version}"],
                log_file,
                check=False
            )

            ensure_image(dotnet_version)

            _csv = OUTPUT_DIR / "builds.csv"

            # ---- debug build ----
            _t = time.time()
            _ok = True
            try:
                run([
                    "docker", "run", "--rm",
                    "-v", f"{app_path}:/source:ro",
                    "-v", f"{out_dir}:/output",
                    "-v", f"{pathlib.Path.home()}/.nuget/packages:/root/.nuget/packages",
                    image_tag(dotnet_version, jdk_version),
                    "bash", "-c",
                    f"""
                set -e
                cp -r /source/. /app
                cd /app

                # ---- strip non-android target frameworks (avoids missing iOS/macOS workload errors) ----
                sed -i 's|<TargetFrameworks>[^<]*</TargetFrameworks>|<TargetFrameworks>net{dotnet_version}.0-android</TargetFrameworks>|' {csproj} 2>/dev/null || true
                sed -i 's|<TargetFramework>[^<]*</TargetFramework>|<TargetFramework>net{dotnet_version}.0-android</TargetFramework>|' {csproj} 2>/dev/null || true

                # ---- restore packages (auto-clean corrupted cache entries on failure) ----
                if ! dotnet restore {csproj} /p:RestorePackagesWithLockFile=true 2>/tmp/nuget_restore.log; then
                    grep -oE "/root/\.nuget/packages/[^/]+/[^/']+" /tmp/nuget_restore.log | sort -u | xargs -r rm -rf 2>/dev/null || true
                    dotnet restore {csproj} /p:RestorePackagesWithLockFile=true || exit 1
                fi

                # ---- build debug APK with per-ABI splits ----
                dotnet build {csproj} \
                    -f net{dotnet_version}.0-android \
                    -c Debug \
                    /p:AndroidCreatePackagePerAbi=true \
                    "/p:AndroidSupportedAbis=armeabi-v7a%3Barm64-v8a%3Bx86%3Bx86_64" \
                    /p:AndroidUseSharedRuntime=false \
                    --no-restore || exit 1

                # ---- verify and copy APKs ----
                APK_DIR="bin/Debug/net{dotnet_version}.0-android"
                if ! ls "$APK_DIR"/*.apk 1>/dev/null 2>&1; then
                    echo "ERROR: No APKs found in $APK_DIR"
                    exit 1
                fi
                cp "$APK_DIR"/*.apk /output/

                # ---- copy metadata ----
                cp {csproj} /output/ || true
                [ -f packages.lock.json ] && cp packages.lock.json /output/ || true
                find . -name "Directory.*.props" 2>/dev/null | grep -v "/bin/" | grep -v "/obj/" | while read f; do cp "$f" /output/ 2>/dev/null; done || true
                find . -name "Directory.*.targets" 2>/dev/null | grep -v "/bin/" | grep -v "/obj/" | while read f; do cp "$f" /output/ 2>/dev/null; done || true
                mkdir -p /output/libs
                find . -name "*.jar" -not -name "gradle-wrapper.jar" 2>/dev/null | grep -v "/bin/" | grep -v "/obj/" | grep -v "/.nuget/" | while read f; do cp "$f" /output/libs/ 2>/dev/null; done || true
                find . -name "*.aar" 2>/dev/null | grep -v "/bin/" | grep -v "/obj/" | grep -v "/.nuget/" | while read f; do cp "$f" /output/libs/ 2>/dev/null; done || true
                find . -name "*.so" 2>/dev/null | grep -v "/bin/" | grep -v "/obj/" | grep -v "/.nuget/" | while read f; do cp "$f" /output/libs/ 2>/dev/null; done || true
                    """
                ], log_file)
            except Exception:
                _ok = False
                raise
            finally:
                record_build(_csv, app_id, "debug", _ok, time.time() - _t)

            # ---- R8 release build ----
            _t = time.time()
            _ok = True
            try:
                run([
                    "docker", "run", "--rm",
                    "-v", f"{app_path}:/source:ro",
                    "-v", f"{out_dir}:/output",
                    "-v", f"{pathlib.Path.home()}/.nuget/packages:/root/.nuget/packages",
                    image_tag(dotnet_version, jdk_version),
                    "bash", "-c",
                    f"""
                set -e
                cp -r /source/. /app
                cd /app

                # ---- strip non-android target frameworks ----
                sed -i 's|<TargetFrameworks>[^<]*</TargetFrameworks>|<TargetFrameworks>net{dotnet_version}.0-android</TargetFrameworks>|' {csproj} 2>/dev/null || true
                sed -i 's|<TargetFramework>[^<]*</TargetFramework>|<TargetFramework>net{dotnet_version}.0-android</TargetFramework>|' {csproj} 2>/dev/null || true

                # ---- build release APKs per-ABI: restore + build inside the loop ----
                # Restoring with -r $ABI_RID populates project.assets.json with a target for that
                # specific RID, preventing NETSDK1047. A single restore without -r only creates a
                # RID-agnostic target, and passing /p:RuntimeIdentifiers="a;b;c" causes NETSDK1083
                # on some SDK versions because the whole string is treated as one unknown RID.
                for ABI_RID in android-arm android-arm64 android-x86 android-x64; do
                    if ! dotnet restore {csproj} /p:RestorePackagesWithLockFile=true -r $ABI_RID 2>/tmp/nuget_restore.log; then
                        grep -oE "/root/\.nuget/packages/[^/]+/[^/']+" /tmp/nuget_restore.log | sort -u | xargs -r rm -rf 2>/dev/null || true
                        dotnet restore {csproj} /p:RestorePackagesWithLockFile=true -r $ABI_RID || true
                    fi
                    dotnet build {csproj} \
                        -f net{dotnet_version}.0-android \
                        -c Release \
                        -r $ABI_RID \
                        /p:AndroidPackageFormat=apk \
                        /p:AndroidUseSharedRuntime=false \
                        /p:AndroidLinkTool=r8 \
                        /p:AndroidLinkMode=SdkOnly \
                        /p:AndroidKeyStore=true \
                        /p:AndroidSigningKeyStore=/root/.android/debug.keystore \
                        /p:AndroidSigningKeyAlias=androiddebugkey \
                        /p:AndroidSigningKeyPass=android \
                        /p:AndroidSigningStorePass=android \
                        --no-restore || true
                    find bin/Release/net{dotnet_version}.0-android -name "*.apk" | while read f; do cp "$f" "/output/r8/$(basename ${{f%.apk}})-$ABI_RID.apk"; done 2>/dev/null || true
                done

                # ---- verify output ----
                if ! ls /output/r8/*.apk 1>/dev/null 2>&1; then
                    echo "ERROR: No APKs copied to /output/r8"
                    exit 1
                fi

                # ---- copy metadata ----
                cp {csproj} /output/r8/ || true
                [ -f packages.lock.json ] && cp packages.lock.json /output/r8/ || true
                find . -name "Directory.*.props" 2>/dev/null | grep -v "/bin/" | grep -v "/obj/" | while read f; do cp "$f" /output/r8/ 2>/dev/null; done || true
                find . -name "Directory.*.targets" 2>/dev/null | grep -v "/bin/" | grep -v "/obj/" | while read f; do cp "$f" /output/r8/ 2>/dev/null; done || true
                mkdir -p /output/r8/libs
                find . -name "*.jar" -not -name "gradle-wrapper.jar" 2>/dev/null | grep -v "/bin/" | grep -v "/obj/" | grep -v "/.nuget/" | while read f; do cp "$f" /output/r8/libs/ 2>/dev/null; done || true
                find . -name "*.aar" 2>/dev/null | grep -v "/bin/" | grep -v "/obj/" | grep -v "/.nuget/" | while read f; do cp "$f" /output/r8/libs/ 2>/dev/null; done || true
                find . -name "*.so" 2>/dev/null | grep -v "/bin/" | grep -v "/obj/" | grep -v "/.nuget/" | while read f; do cp "$f" /output/r8/libs/ 2>/dev/null; done || true
                    """
                ], log_file)
            except Exception:
                _ok = False
                raise
            finally:
                record_build(_csv, app_id, "r8", _ok, time.time() - _t)

            run(
                ["echo", f"Build succeeded with .NET {dotnet_version}"],
                log_file,
                check=False
            )

            print(f"[done] {app_id} ({dotnet_version})")
            return

        except Exception as e:
            run(
                ["echo", f"Build failed with .NET {dotnet_version} and JDK {jdk_version}: {e}"],
                log_file,
                check=False
            )

        dotnet_version = next_dotnet_version(dotnet_version)

    with log_file.open("a") as f:
        f.write("\nERROR: All .NET versions failed\n")

    print(f"[failed] {app_id} (all versions)")


# ---------- main ----------

def main():
    apps = load_manifest(ROOT)
    run_builds(build_app, apps, OUTPUT_DIR)


if __name__ == "__main__":
    main()
