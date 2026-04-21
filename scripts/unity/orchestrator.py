import pathlib
import re
import threading
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from scripts.common.helpers import run, load_manifest, image_exists, run_builds  # noqa: F401

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
DOCKERFILE_DIR = ROOT
GLOBAL_LOG = OUTPUT_DIR / "build.log"
IMAGE_PREFIX = "unity-android"
BUILD_LOCKS = {}  # (unity_version, jdk_version) -> Lock
GLOBAL_LOCK = threading.Lock()

# Ordered list of supported Unity versions (oldest → newest).
# The orchestrator starts at the version declared in the project and escalates
# upward if the build fails (forward-compat is safer than downgrading).
UNITY_VERSIONS = [
    "2019.4.40f1",
    "2020.3.48f1",
    "2021.3.45f1",
    "2022.3.54f1",
    "2023.2.20f1",
    "6000.0.26f1",
]

_VERSION_CLEAN_RE = re.compile(r"[a-z]\d+$")


# ---------- helpers ----------

def pick_jdk(unity_version: str) -> int:
    """Unity 2022+ and Unity 6 (6000.x) require JDK 17; older versions use JDK 11."""
    major = int(unity_version.split(".")[0])
    if major >= 2022 or major >= 6000:
        return 17
    return 11


def _clean_ver(v: str) -> tuple[int, ...]:
    """Strip alpha/beta/release suffix and return a comparable int tuple."""
    base = _VERSION_CLEAN_RE.sub("", v)
    return tuple(int(x) for x in base.split("."))


def snap_to_supported(unity_version: str) -> str:
    """
    Return the first supported version that is >= the requested version.
    Falls back to the latest if the project is newer than all known versions.
    """
    pv = _clean_ver(unity_version)
    for sv in UNITY_VERSIONS:
        if _clean_ver(sv) >= pv:
            return sv
    return UNITY_VERSIONS[-1]


def next_unity_version(current: str) -> str | None:
    try:
        idx = UNITY_VERSIONS.index(current)
    except ValueError:
        return None
    if idx + 1 < len(UNITY_VERSIONS):
        return UNITY_VERSIONS[idx + 1]
    return None


# ---------- docker image handling ----------

def image_tag(unity_version: str, jdk_version: int) -> str:
    return f"{IMAGE_PREFIX}:{unity_version}-jdk{jdk_version}"


def ensure_image(unity_version: str):
    jdk_version = pick_jdk(unity_version)
    tag = image_tag(unity_version, jdk_version)

    if image_exists(tag):
        return

    key = (unity_version, jdk_version)

    with GLOBAL_LOCK:
        lock = BUILD_LOCKS.setdefault(key, threading.Lock())

    with lock:
        if image_exists(tag):
            return

        print(f"[image] building {tag}  (this may take 10–20 min; Unity is large)")
        run([
            "docker", "build",
            "--build-arg", f"UNITY_VERSION={unity_version}",
            "--build-arg", f"JDK_VERSION={jdk_version}",
            "-t", tag,
            str(DOCKERFILE_DIR),
        ], GLOBAL_LOG, check=True)
        if not image_exists(tag):
            raise RuntimeError(f"Image build failed for {tag}")


# ---------- build execution ----------

def _license_volume() -> list[str]:
    """
    Mount the host Unity license file into the container if it exists.
    Activate a Unity Personal license once via:
        unity-editor -batchmode -quit -createManualActivationFile -logFile
    then submit the .alf at https://license.unity3d.com and save the .ulf to
    ~/.local/share/unity3d/Unity/Unity_lic.ulf on the host machine.
    """
    lic = pathlib.Path.home() / ".local/share/unity3d/Unity/Unity_lic.ulf"
    if lic.exists():
        return ["-v", f"{lic}:/root/.local/share/unity3d/Unity/Unity_lic.ulf:ro"]
    return []


def build_app(app):
    app_id = app["id"]
    raw_unity_version = str(app["unity"])
    app_path = ROOT / app["path"]

    out_dir = OUTPUT_DIR / app_id
    out_dir.mkdir(parents=True, exist_ok=True)
    r8_dir = out_dir / "r8"
    r8_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "build.log"
    log_file.write_text("")

    # Start from the closest supported version that is >= the project's version
    unity_version = snap_to_supported(raw_unity_version)
    attempts = 0
    max_attempts = len(UNITY_VERSIONS)

    license_vol = _license_volume()

    while unity_version and attempts < max_attempts:
        attempts += 1
        jdk_version = pick_jdk(unity_version)

        try:
            run(
                ["echo", f"Attempting build for {app_id} with Unity {unity_version} (JDK {jdk_version})"],
                log_file,
                check=False,
            )

            ensure_image(unity_version)

            # Unity executable path inside the container (installed by Unity Hub as root)
            unity_exe = f"/root/Unity/Hub/Editor/{unity_version}/Editor/Unity"
            # Common Unity Hub install layout; fall back to a find if path differs
            unity_launch = (
                f'UNITY_EXE="{unity_exe}"; '
                f'[ -x "$UNITY_EXE" ] || UNITY_EXE=$(find /root/Unity -name "Unity" -type f 2>/dev/null | head -1); '
                f'[ -n "$UNITY_EXE" ] || {{ echo "ERROR: Unity executable not found"; exit 1; }}'
            )

            # ---- debug build ----
            run([
                "docker", "run", "--rm",
                *license_vol,
                "-v", f"{app_path}:/source:ro",
                "-v", f"{out_dir}:/output",
                image_tag(unity_version, jdk_version),
                "bash", "-c",
                f"""
                set -e

                # ---- copy project (source is read-only) ----
                cp -r /source/. /app
                cd /app

                # ---- inject build helper script ----
                mkdir -p Assets/Editor
                cp /opt/BuildScript.cs Assets/Editor/BuildScript.cs

                # ---- locate Unity executable ----
                {unity_launch}

                # ---- debug build ----
                xvfb-run -a "$UNITY_EXE" \\
                    -batchmode \\
                    -nographics \\
                    -quit \\
                    -projectPath /app \\
                    -buildTarget Android \\
                    -executeMethod BuildScript.BuildDebug \\
                    -accept-apiupdate \\
                    -logFile /proc/1/fd/1 || exit 1

                # ---- verify output ----
                ls /output/app-debug.apk 1>/dev/null 2>&1 || {{ echo "ERROR: debug APK not produced"; exit 1; }}

                # ---- copy TPL metadata ----
                [ -f Packages/manifest.json ] && cp Packages/manifest.json /output/ || true
                [ -f Packages/packages-lock.json ] && cp Packages/packages-lock.json /output/ || true
                """
            ], log_file)

            # ---- release build (IL2CPP + R8) ----
            run([
                "docker", "run", "--rm",
                *license_vol,
                "-v", f"{app_path}:/source:ro",
                "-v", f"{out_dir}:/output",
                image_tag(unity_version, jdk_version),
                "bash", "-c",
                f"""
                set -e

                # ---- copy project ----
                cp -r /source/. /app
                cd /app

                # ---- inject build helper script ----
                mkdir -p Assets/Editor
                cp /opt/BuildScript.cs Assets/Editor/BuildScript.cs

                # ---- locate Unity executable ----
                {unity_launch}

                # ---- release build (4 ABIs) ----
                xvfb-run -a "$UNITY_EXE" \\
                    -batchmode \\
                    -nographics \\
                    -quit \\
                    -projectPath /app \\
                    -buildTarget Android \\
                    -executeMethod BuildScript.BuildRelease \\
                    -accept-apiupdate \\
                    -logFile /proc/1/fd/1 || exit 1

                # ---- verify output ----
                ls /output/r8/*.apk 1>/dev/null 2>&1 || {{ echo "ERROR: no release APKs produced"; exit 1; }}

                # ---- copy TPL metadata ----
                [ -f Packages/manifest.json ] && cp Packages/manifest.json /output/r8/ || true
                [ -f Packages/packages-lock.json ] && cp Packages/packages-lock.json /output/r8/ || true
                """
            ], log_file)

            run(
                ["echo", f"Build succeeded with Unity {unity_version}"],
                log_file,
                check=False,
            )

            print(f"[done] {app_id} ({unity_version})")
            return

        except Exception as e:
            run(
                ["echo", f"Build failed with Unity {unity_version}: {e}"],
                log_file,
                check=False,
            )

        unity_version = next_unity_version(unity_version)

    with log_file.open("a") as f:
        f.write("\nERROR: All Unity versions failed\n")

    print(f"[failed] {app_id} (all versions)")


# ---------- main ----------

def main():
    apps = load_manifest(ROOT)
    run_builds(build_app, apps, OUTPUT_DIR)


if __name__ == "__main__":
    main()
