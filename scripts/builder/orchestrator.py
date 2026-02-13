import subprocess
import yaml
import pathlib
import threading
import os
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
DOCKERFILE_DIR = ROOT

IMAGE_PREFIX = "flutter-android"
BUILD_LOCKS = {}  # (flutter_version, jdk_version) -> Lock
GLOBAL_LOCK = threading.Lock()


# ---------- helpers ----------

def run(cmd, check=True):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, check=check)


def load_manifest():
    with open(ROOT / "build_manifest.yaml") as f:
        return yaml.safe_load(f)["apps"]


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


def image_exists(tag: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


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
        ])


# ---------- build execution ----------

def build_app(app):
    app_id = app["id"]
    flutter_version = app["flutter"]
    jdk_version = pick_jdk(flutter_version)
    app_path = ROOT / app["path"]
    output_type = app.get("output", "apk")

    ensure_image(flutter_version)

    out_dir = OUTPUT_DIR / app_id
    out_dir.mkdir(parents=True, exist_ok=True)

    build_cmd = (
        "flutter pub get && "
        f"flutter build {output_type} --debug "
        f"2>&1 | tee /out/{app_id}.log"
    )

    run([
        "docker", "run", "--rm",
        "-v", f"{app_path}:/app",
        "-v", f"{out_dir}:/out",
        "-v", f"{pathlib.Path.home()}/.pub-cache:/root/.pub-cache",
        image_tag(flutter_version, jdk_version),
        "bash", "-c", build_cmd,
    ], check=True)

    print(f"[done] {app_id}")


# ---------- main ----------

def main():
    apps = load_manifest()
    OUTPUT_DIR.mkdir(exist_ok=True)

    max_parallel = max(1, (os.cpu_count() or 2) // 2)

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        pool.map(build_app, apps)


if __name__ == "__main__":
    main()
