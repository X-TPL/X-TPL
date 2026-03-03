import json
import yaml
from pathlib import Path
import re
import os

from typing import Dict, List

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
        return match.group()

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


def analyze_react_native_buildability(repo_root: Path) -> Dict:
    """
    Analyze a repository and determine whether it is:
        - buildable with Gradle (bare React Native)
        - buildable with Expo
        - not buildable"""

    def load_package_json(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def is_library(pkg_data: dict) -> bool:
        """
        Detect common RN library patterns:
        - react-native only in peerDependencies
        - no android/ and no expo config
        """
        deps = pkg_data.get("dependencies", {})
        peer_deps = pkg_data.get("peerDependencies", {})

        has_rn_dep = "react-native" in deps
        has_rn_peer = "react-native" in peer_deps

        # library pattern: peerDep but not dependency
        if has_rn_peer and not has_rn_dep:
            return True

        return False

    # Find all package.json files except inside node_modules
    package_files : List[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        # Skip node_modules entirely
        if "node_modules" in dirnames:
            dirnames.remove("node_modules")  # prevents os.walk from descending

        if "package.json" in filenames:
            package_files.append(Path(dirpath) / "package.json")

    for pkg_file in package_files:
        pkg_dir = pkg_file.parent
        pkg_data = load_package_json(pkg_file)

        if not pkg_data:
            continue

        deps = {
            **pkg_data.get("dependencies", {}),
            **pkg_data.get("devDependencies", {})
        }

        # Skip obvious libraries
        if is_library(pkg_data):
            continue

        has_rn = "react-native" in deps
        has_expo = "expo" in deps

        # ---- Gradle Build Detection ----
        gradlew_path = pkg_dir / "android" / "gradlew"

        if has_rn and gradlew_path.exists():
            return "gradle"

        # ---- Expo Build Detection ----
        app_json = pkg_dir / "app.json"
        app_config_js = pkg_dir / "app.config.js"

        if has_expo and (app_json.exists() or app_config_js.exists()):
            return "expo"

    return None

# -------------------------
# Analyzer
# -------------------------


def analyze():
    apps = []

    for repo_dir in EXTRACT_ROOT.iterdir():
        if not repo_dir.is_dir():
            continue

        subdirs = [d for d in repo_dir.iterdir() if d.is_dir()]
        dir = None
        if len(subdirs) == 1:
            dir = subdirs[0]  # override to point to real repo
        
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
                if buildability is None:
                    raise Exception("not buildable")
                
                app_entry = {
                    "id": repo_dir.name if len(candidates) == 1 else f"{repo_dir.name}-{counter}",
                    "path": normalize_path(base_dir),
                    "node": node_version,
                    "type": buildability,
                    "output": "apk"
                }
                counter += 1
                apps.append(app_entry)
                print(f"[ok] {repo_dir.name}")

            except Exception as e:
                print(f"[skip] {repo_dir.name}: {e}")

    manifest = {"apps": apps}

    with open(OUTPUT_FILE, "w") as f:
        yaml.safe_dump(
            manifest,
            f,
            sort_keys=False,
            default_flow_style=False,
        )

    print(f"\nGenerated {len(apps)} build entries.")


if __name__ == "__main__":
    analyze()
