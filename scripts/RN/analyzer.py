import json
import yaml
from pathlib import Path
import re
import os

EXTRACT_ROOT = Path("/home/ubuntu/storage/rn_assets/extracted")
OUTPUT_FILE = "build_manifest.yaml"

# -------------------------
# Utilities
# -------------------------

def normalize_path(path: Path) -> str:
    return str(path.as_posix())


def _normalize_node_version(version_str: str) -> str:
    """
    Extract first numeric major version from:
    '>=16'
    '^18.17.0'
    '>=20.17.0 || >=22.9.0'
    '18.x'
    'v20'
    """
    if not version_str:
        return "18"

    match = re.search(r"\d+", version_str)
    if match:
        return match.group() if int(match.group()) >= 16 else "16"

    return "18"


def extract_node_version(project_dir) -> str:
    data = json.loads((project_dir / "package.json").read_text())

    # 1️⃣ Volta (most reliable)
    if "volta" in data and "node" in data["volta"]:
        return _normalize_node_version(data["volta"]["node"])

    # 2️⃣ engines
    if "engines" in data and "node" in data["engines"]:
        return _normalize_node_version(data["engines"]["node"])

    # 3️⃣ .nvmrc
    nvmrc = project_dir / ".nvmrc"
    if nvmrc.exists():
        return _normalize_node_version(nvmrc.read_text().strip())

    return "18"  # safe default

def extract_gradle_version(project_path: Path) -> str | None:
    wrapper_file = project_path / "android" / "gradle" / "wrapper" / "gradle-wrapper.properties"

    if not wrapper_file.exists():
        return None

    content = wrapper_file.read_text(encoding="utf-8")

    match = re.search(r"gradle-(\d+\.\d+(?:\.\d+)?)", content)
    if match:
        return match.group(1)

    return None
def predict_jdk_from_gradle(gradle_version: str | None) -> int:
    if not gradle_version:
        return 17  # safe modern default

    major = int(gradle_version.split(".")[0])
    minor = int(gradle_version.split(".")[1])

    if major <= 6:
        return 8

    if major == 7:
        if minor <= 2:
            return 11
        return 17

    if major >= 8:
        return 17

    return 17

def expo_has_android_package(pkg_dir: Path) -> bool:
    app_json = pkg_dir / "app.json"
    app_config_js = pkg_dir / "app.config.js"

    # ---- Case 1: app.json ----
    if app_json.exists():
        try:
            data = json.loads(app_json.read_text(encoding="utf-8"))

            # Expo config can be nested under "expo"
            expo_config = data.get("expo", data)

            android = expo_config.get("android", {})
            if isinstance(android, dict) and android.get("package"):
                return True
        except Exception:
            return False

    # ---- Case 2: app.config.js ----
    if app_config_js.exists():
        try:
            content = app_config_js.read_text(encoding="utf-8")

            # Simple heuristic: check for android.package string
            if re.search(r"android\s*:\s*{[^}]*package\s*:", content, re.DOTALL):
                return True
        except Exception:
            return False

    return False

def analyze_react_native_buildability(pkg_dir: Path) -> str | None:
    pkg_file = pkg_dir / "package.json"

    if not pkg_file.exists():
        return None

    try:
        pkg_data = json.loads(pkg_file.read_text(encoding="utf-8"))
    except Exception:
        print("[info] failed to load package.json")
        return None

    deps = {
        **pkg_data.get("dependencies", {}),
        **pkg_data.get("devDependencies", {})
    }

    # ---- library detection ----
    peer_deps = pkg_data.get("peerDependencies", {})
    if "react-native" in peer_deps and "react-native" not in deps:
        print("[info] Repo is library")
        return None

    has_rn = "react-native" in deps
    has_expo = "expo" in deps

    android_dir = pkg_dir / "android"
    gradlew_path = android_dir / "gradlew"

    # ---- Gradle project ----
    if has_rn and android_dir.exists() and gradlew_path.exists():
        return "gradle"

    # ---- Expo project ----
    if has_expo and expo_has_android_package(pkg_dir):
        return "expo"

    return None

# -------------------------
# Analyzer
# -------------------------


def analyze():
    apps = []
    duplicated_repos = 0
    total_repos = 0
    for repo_dir in EXTRACT_ROOT.iterdir():
        if not repo_dir.is_dir():
            continue

        subdirs = [d for d in repo_dir.iterdir() if d.is_dir()]
        dir = None
        if len(subdirs) == 1:
            dir = subdirs[0] 
        
        candidates = []
        for dirpath, dirnames, filenames in os.walk(dir):
            # Skip node_modules entirely
            if "node_modules" in dirnames:
                dirnames.remove("node_modules")  # prevents os.walk from descending

            if "package.json" in filenames:
                candidates.append(Path(dirpath) / "package.json")
        counter = 0
        for package_path in candidates:
            base_dir = package_path.parent

            try:

                node_version = extract_node_version(base_dir)
                buildability = analyze_react_native_buildability(base_dir)
                gradle_version = extract_gradle_version(base_dir)
                jdk_version = predict_jdk_from_gradle(gradle_version)
                if buildability is None:
                    raise Exception("not buildable")
                
                app_entry = {
                    "id": repo_dir.name if len(candidates) == 1 else f"{repo_dir.name}-{counter}",
                    "path": normalize_path(base_dir),
                    "node": node_version,
                    "type": buildability,
                    "jdk": jdk_version, 
                    "output": "apk"
                }
                counter += 1
                apps.append(app_entry)
                print(f"[ok] {repo_dir.name}")

            except Exception as e:
                print(f"[skip] {repo_dir.name}: {e}")
        if counter > 1:
            duplicated_repos += 1
            total_repos += counter

    manifest = {"apps": apps}

    with open(OUTPUT_FILE, "w") as f:
        yaml.safe_dump(
            manifest,
            f,
            sort_keys=False,
            default_flow_style=False,
        )

    print(f"\nGenerated {len(apps)} build entries.")
    print(f"\n{duplicated_repos} had multiple build entries")
    print(f"\n{total_repos} build entries originate from duplicated repos")


if __name__ == "__main__":
    analyze()
