import time
import yaml
import pathlib
import threading
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from scripts.common.helpers import run, load_manifest, image_exists, run_builds, record_build

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
DOCKERFILE_DIR = ROOT
GLOBAL_LOG = OUTPUT_DIR / "build.log"
IMAGE_PREFIX = "flutter-android"
BUILD_LOCKS = {}  # (flutter_version, jdk_version) -> Lock
GLOBAL_LOCK = threading.Lock()

# Ordered list of known Flutter versions (ascending)
FLUTTER_VERSIONS = [
    "1.17.0",
    "1.20.0",
    "1.22.0",
    "2.0.0",
    "2.2.0",
    "2.5.0",
    "2.8.0",
    "2.10.0",
    "3.0.0",
    "3.7.0",
    "3.13.0",
    "3.16.0",
    "3.19.0",
    "3.22.0",
    "3.24.0",
    "3.32.0",
    "3.35.0",
    "3.38.0",
    "3.41.0",
    "3.41.2" # latest build as of 24.02.26
]


# ---------- helpers ----------

def next_flutter_version(current: str):
    try:
        idx = FLUTTER_VERSIONS.index(current)
    except ValueError:
        return None

    if idx + 1 < len(FLUTTER_VERSIONS):
        return FLUTTER_VERSIONS[idx + 1]

    return None


def get_missing_assets(app_path: pathlib.Path):
    pubspec_path = app_path / "pubspec.yaml"
    if not pubspec_path.exists():
        return []

    data = yaml.safe_load(pubspec_path.read_text()) or {}
    flutter_section = data.get("flutter", {})
    assets = flutter_section.get("assets", [])

    if not isinstance(assets, list):
        return []

    missing = []

    for asset in assets:
        asset_path = app_path / asset

        if asset.endswith("/"):
            if not asset_path.exists():
                missing.append(asset.rstrip("/"))
        else:
            if not asset_path.exists():
                missing.append(asset)

    return missing

def create_asset_cmd(missing_assets):
    asset_creation_cmds = []
    for asset in missing_assets:
        if "." in pathlib.Path(asset).name:
            # treat as file
            asset_creation_cmds.append(
                f'mkdir -p "$(dirname \\"{asset}\\")" && touch "{asset}"'
            )
        else:
            # treat as directory
            asset_creation_cmds.append(
                f'mkdir -p "{asset}"'
            )
    if not asset_creation_cmds:
        # no assets → just return true (does nothing)
        return "true"
    asset_script = " && \\\n                ".join(asset_creation_cmds)
    return asset_script

# ---------- JDK selection logic ----------

def pick_jdk(flutter_version: str) -> int:
    major, minor, *_ = map(int, flutter_version.split("."))

    # Flutter 3.16+ typically requires newer AGP -> JDK 17
    if major > 3 or (major == 3 and minor >= 16):
        return 17

    return 11


# ---------- docker image handling ----------

def image_tag(flutter_version: str, jdk_version: int) -> str:
    return f"{IMAGE_PREFIX}:{flutter_version}-jdk{jdk_version}"


def ensure_image(flutter_version: str):
    jdk_version = pick_jdk(flutter_version)
    tag = image_tag(flutter_version, jdk_version)

    if image_exists(tag):
        return

    # one lock per flutter+jdk combo
    key = (flutter_version, jdk_version)

    with GLOBAL_LOCK:
        lock = BUILD_LOCKS.setdefault(key, threading.Lock())

    with lock:
        if image_exists(tag):
            return

        print(f"[image] building {tag}")
        run([
            "docker", "build",
            "--build-arg", f"FLUTTER_VERSION={flutter_version}",
            "--build-arg", f"JDK_VERSION={jdk_version}",
            "-t", tag,
            str(DOCKERFILE_DIR),
        ], GLOBAL_LOG, check=True)
        if not image_exists(tag):
            raise RuntimeError(f"Image build failed for {tag}")


# ---------- build execution ----------

def build_app(app):
    attempts = 0
    max_attempts = len(FLUTTER_VERSIONS)
    app_id = app["id"]
    flutter_version = app["flutter"]
    output_type = app.get("output", "apk")
    app_path = ROOT / app["path"]

    out_dir = OUTPUT_DIR / app_id
    out_dir.mkdir(parents=True, exist_ok=True)
    r8_dir = out_dir / "r8"
    r8_dir.mkdir(parents=True, exist_ok=True)
    obfus_dir = out_dir / "obfuscated"
    obfus_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "build.log"
    log_file.write_text("")
    missing_assets = get_missing_assets(app_path)
    assets = create_asset_cmd(missing_assets)
    while flutter_version and attempts < max_attempts:
        attempts += 1
        jdk_version = pick_jdk(flutter_version)

        try:
            run(
                ["echo", f"Attempting build for {app_id} with Flutter {flutter_version} and jdk {jdk_version}"],
                log_file,
                check=False
            )

            ensure_image(flutter_version)

            _csv = OUTPUT_DIR / "builds.csv"

            _t = time.time()
            _ok = True
            try:
                run([
                    "docker", "run", "--rm",
                    "-v", f"{app_path}:/source:ro",
                    "-v", f"{out_dir}:/output",
                    "-v", f"{pathlib.Path.home()}/.pub-cache:/root/.pub-cache",
                    image_tag(flutter_version, jdk_version),
                    "bash", "-c",
                    f"""
                cp -r /source/. /app && \
                cd /app && \
                {assets} && \
                flutter clean && \
                flutter pub get && \
                (./gradlew clean || true) && \
                if grep -R "part '.*\\.g\\.dart'" lib >/dev/null 2>&1; then \
                    flutter pub run build_runner build --delete-conflicting-outputs || true; \
                fi && \
                flutter build {output_type} --debug --no-pub --split-per-abi && \
                cp build/app/outputs/flutter-apk/*.apk /output/ && \
                cp .dart_tool/package_config.json /output/ && \
                cp pubspec.lock /output/
                    """
                ], log_file)
            except Exception:
                _ok = False
                raise
            finally:
                record_build(_csv, app_id, "debug", _ok, time.time() - _t)

            _t = time.time()
            _ok = True
            try:
                run([ # R8 obfuscation
                    "docker", "run", "--rm",
                    "-v", f"{app_path}:/source:ro",
                    "-v", f"{out_dir}:/output",
                    "-v", f"{pathlib.Path.home()}/.pub-cache:/root/.pub-cache",
                    image_tag(flutter_version, jdk_version),
                    "bash", "-c",
                    f"""
                cp -r /source/. /app && \
                cd /app && \
                {assets} && \
                flutter clean && \
                flutter pub get && \
                (./gradlew clean || true) && \
                if grep -R "part '.*\\.g\\.dart'" lib >/dev/null 2>&1; then \
                    flutter pub run build_runner build --delete-conflicting-outputs || true; \
                fi && \
                sed -i 's/signingConfig signingConfigs\.release/signingConfig signingConfigs.debug/' android/app/build.gradle || true && \
                flutter build {output_type} --release --no-pub --split-per-abi && \
                cp build/app/outputs/flutter-apk/*.apk /output/r8/ && \
                cp .dart_tool/package_config.json /output/r8/ && \
                cp pubspec.lock /output/r8/
                    """
                ], log_file)
            except Exception:
                _ok = False
                raise
            finally:
                record_build(_csv, app_id, "r8", _ok, time.time() - _t)

            _t = time.time()
            _ok = True
            try:
                run([ # Flutter obfuscation
                    "docker", "run", "--rm",
                    "-v", f"{app_path}:/source:ro",
                    "-v", f"{out_dir}:/output",
                    "-v", f"{pathlib.Path.home()}/.pub-cache:/root/.pub-cache",
                    image_tag(flutter_version, jdk_version),
                    "bash", "-c",
                    f"""
                cp -r /source/. /app && \
                cd /app && \
                {assets} && \
                flutter clean && \
                flutter pub get && \
                (./gradlew clean || true) && \
                if grep -R "part '.*\\.g\\.dart'" lib >/dev/null 2>&1; then \
                    flutter pub run build_runner build --delete-conflicting-outputs || true; \
                fi && \
                sed -i 's/signingConfig signingConfigs\.release/signingConfig signingConfigs.debug/' android/app/build.gradle || true && \
                flutter build {output_type} --release --obfuscate --split-debug-info=/output/obfuscated/ --no-pub --split-per-abi && \
                cp build/app/outputs/flutter-apk/*.apk /output/obfuscated/ && \
                cp .dart_tool/package_config.json /output/obfuscated/ && \
                cp pubspec.lock /output/obfuscated/
                    """
                ], log_file)
            except Exception:
                _ok = False
                raise
            finally:
                record_build(_csv, app_id, "obfuscated", _ok, time.time() - _t)

            run(
                ["echo", f"Build succeeded with Flutter {flutter_version}"],
                log_file,
                check=False
            )

            print(f"[done] {app_id} ({flutter_version})")
            return

        except Exception as e:
            run(
                ["echo", f"Build failed with Flutter {flutter_version} and jdk version {jdk_version} with the following error: {e}"],
                log_file,
                check=False
            )

            flutter_version = next_flutter_version(flutter_version)

    # If we exit loop → all versions failed
    with log_file.open("a") as f:
        f.write("\nERROR: All Flutter versions failed\n")

    print(f"[failed] {app_id} (all versions)")




# ---------- main ----------

def main():
    apps = load_manifest(ROOT)
    run_builds(build_app, apps, OUTPUT_DIR)


if __name__ == "__main__":
    main()
