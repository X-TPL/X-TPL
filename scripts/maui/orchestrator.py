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
IMAGE_PREFIX = "maui-android"
BUILD_LOCKS = {}  # (dotnet_version, jdk_version) -> Lock
GLOBAL_LOCK = threading.Lock()

DOTNET_VERSIONS = [6, 7, 8, 9]


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
        except subprocess.TimeoutExpired:
            f.write("\nERROR: Command timed out\n")
            raise

        f.write(result.stdout)

        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd)


def load_manifest():
    with open(ROOT / "build_manifest.yaml") as f:
        return yaml.safe_load(f)["apps"]


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


def image_exists(tag: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


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

            # ---- debug build ----
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
                if ! dotnet restore {csproj} 2>/tmp/nuget_restore.log; then
                    grep -oE "/root/\.nuget/packages/[^/]+/[^/']+" /tmp/nuget_restore.log | sort -u | xargs -r rm -rf 2>/dev/null || true
                    dotnet restore {csproj} || exit 1
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
                """
            ], log_file)

            # ---- R8 release build ----
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

                # ---- restore packages (auto-clean corrupted cache entries on failure) ----
                if ! dotnet restore {csproj} 2>/tmp/nuget_restore.log; then
                    grep -oE "/root/\.nuget/packages/[^/]+/[^/']+" /tmp/nuget_restore.log | sort -u | xargs -r rm -rf 2>/dev/null || true
                    dotnet restore {csproj} || exit 1
                fi

                # ---- build release APKs per-ABI via RuntimeIdentifier ----
                for ABI_RID in android-arm android-arm64 android-x86 android-x64; do
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
                        --no-restore || exit 1
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
                """
            ], log_file)

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
    apps = load_manifest()
    OUTPUT_DIR.mkdir(exist_ok=True)

    max_parallel = max(1, (os.cpu_count() or 2) // 2)
    futures = []
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        for app in apps:
            futures.append(pool.submit(build_app, app))

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"[executor error] {e}")


if __name__ == "__main__":
    main()
