import json
import yaml
from pathlib import Path
import re
import os
import xml.etree.ElementTree as ET

EXTRACT_ROOT = Path("/home/ubuntu/storage/cordova_assets/extracted")
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

def get_required_jdk(pkg_dir: Path) -> int | None:
    cordova_android_version = None

    # --- 1. Check package.json ---
    pkg_file = pkg_dir / "package.json"
    if pkg_file.exists():
        try:
            pkg = json.loads(pkg_file.read_text(encoding="utf-8"))

            deps = pkg.get("dependencies", {})
            dev_deps = pkg.get("devDependencies", {})

            version = deps.get("cordova-android") or dev_deps.get("cordova-android")

            if version:
                cordova_android_version = version
        except Exception:
            pass

    # --- 2. Check config.xml ---
    if cordova_android_version is None:
        config_file = pkg_dir / "config.xml"
        if config_file.exists():
            try:
                root = ET.fromstring(config_file.read_text(encoding="utf-8"))

                for elem in root.iter():
                    if elem.tag.endswith("engine") and elem.attrib.get("name") == "android":
                        cordova_android_version = elem.attrib.get("spec")
                        break
            except Exception:
                pass

    # --- 3. Check committed platform version ---
    if cordova_android_version is None:
        version_file = pkg_dir / "platforms/android/cordova/version"
        if version_file.exists():
            try:
                cordova_android_version = version_file.read_text().strip()
            except Exception:
                pass

    if cordova_android_version is None:
        return None

    # Extract major version
    match = re.search(r"\d+", cordova_android_version)
    if not match:
        return None

    major = int(match.group())

    # Map cordova-android -> JDK
    if major >= 12:
        return 17
    elif major >= 10:
        return 11
    else:
        return 8

def is_cordova_android_project(paths, file_contents):
    """
    paths: set/list of all file paths in repo
    file_contents: dict {path: file_text} for files we may parse
    """

    # Must at least look like a Cordova project
    if "config.xml" not in paths or "www/index.html" not in paths:
        return False

    # ---- Check package.json ----
    if "package.json" in file_contents:
        try:
            pkg = json.loads(file_contents["package.json"])

            # dependencies
            deps = pkg.get("dependencies", {})
            dev_deps = pkg.get("devDependencies", {})

            if "cordova-android" in deps or "cordova-android" in dev_deps:
                return True

            # cordova platform list
            cordova = pkg.get("cordova", {})
            if "android" in cordova.get("platforms", []):
                return True
        except Exception:
            pass

    # ---- Check config.xml ----
    if "config.xml" in file_contents:
        try:
            root = ET.fromstring(file_contents["config.xml"])

            for elem in root.iter():
                if elem.tag.endswith("engine") and elem.attrib.get("name") == "android":
                    return True
                if elem.tag.endswith("platform") and elem.attrib.get("name") == "android":
                    return True
        except Exception:
            pass

    # ---- Check committed platform ----
    for p in paths:
        if p.startswith("platforms/android/") or p == "platforms/android":
            return True

    return False

def analyze_buildability(pkg_dir: Path) -> bool:
    paths = set()
    file_contents = {}

    # Collect all file paths
    for p in pkg_dir.rglob("*"):
        if p.is_file():
            rel = p.relative_to(pkg_dir).as_posix()
            paths.add(rel)

    # Load package.json
    pkg_file = pkg_dir / "package.json"
    if pkg_file.exists():
        try:
            file_contents["package.json"] = pkg_file.read_text(encoding="utf-8")
        except Exception:
            print("[info] failed to read package.json")

    # Load config.xml
    config_file = pkg_dir / "config.xml"
    if config_file.exists():
        try:
            file_contents["config.xml"] = config_file.read_text(encoding="utf-8")
        except Exception:
            print("[info] failed to read config.xml")

    return is_cordova_android_project(paths, file_contents)

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
                buildability = analyze_buildability(base_dir)
                jdk_version = get_required_jdk(base_dir)
                if buildability is None:
                    raise Exception("not buildable")
                
                app_entry = {
                    "id": repo_dir.name if len(candidates) == 1 else f"{repo_dir.name}-{counter}",
                    "path": normalize_path(base_dir),
                    "node": node_version,
                    "jdk": jdk_version, 
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
