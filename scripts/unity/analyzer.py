"""
Analyze extracted Unity repos and produce build_manifest.yaml.

Detection criteria:
  - ProjectSettings/ProjectVersion.txt  →  m_EditorVersion: 2022.3.15f1
  - At least one .unity scene file under Assets/
  - Packages/manifest.json present (Unity Package Manager)

The manifest entry records the exact Unity version from the project so the
orchestrator can build with the closest supported version.
"""

import os
import re
import yaml
from pathlib import Path

EXTRACT_ROOT = Path("/home/ubuntu/storage/unity_assets/extracted")
OUTPUT_FILE = "build_manifest.yaml"

SKIP_DIRS = {".git", "Library", "Temp", "Logs", "obj", "Build"}

VERSION_RE = re.compile(r"m_EditorVersion:\s*([0-9]+\.[0-9]+\.[0-9]+[a-z][0-9]+)")


# -------------------------
# Utilities
# -------------------------

def normalize_path(path: Path) -> str:
    return str(path.as_posix())


def pick_jdk(unity_version: str) -> int:
    """Unity 2022+ / Unity 6 (6000.x) require JDK 17; older versions use JDK 11."""
    major = int(unity_version.split(".")[0])
    # Unity 6 is versioned as 6000.x; treat anything >= 2022 or >= 6000 as needing JDK 17
    if major >= 2022 or major >= 6000:
        return 17
    return 11


def extract_unity_version(project_root: Path) -> str | None:
    """Read ProjectSettings/ProjectVersion.txt and return the editor version string."""
    version_file = project_root / "ProjectSettings" / "ProjectVersion.txt"
    if not version_file.exists():
        return None
    try:
        content = version_file.read_text(encoding="utf-8", errors="ignore")
        match = VERSION_RE.search(content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def has_scenes(project_root: Path) -> bool:
    """Return True if at least one .unity scene exists under Assets/."""
    assets_dir = project_root / "Assets"
    if not assets_dir.is_dir():
        return False
    for dirpath, dirnames, filenames in os.walk(assets_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if any(f.endswith(".unity") for f in filenames):
            return True
    return False


def has_upm_manifest(project_root: Path) -> bool:
    """Return True if Unity Package Manager manifest.json is present."""
    return (project_root / "Packages" / "manifest.json").exists()


# -------------------------
# Analyzer
# -------------------------

def analyze():
    apps = []

    for repo_dir in sorted(EXTRACT_ROOT.iterdir()):
        if not repo_dir.is_dir():
            continue

        # GitHub archives unzip to a single subdirectory; unwrap it if present
        subdirs = [d for d in repo_dir.iterdir() if d.is_dir()]
        root_dir = subdirs[0] if len(subdirs) == 1 else repo_dir

        app_entry = None

        # Walk to find the Unity project root (has ProjectSettings/ProjectVersion.txt)
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            base_dir = Path(dirpath)
            unity_version = extract_unity_version(base_dir)
            if unity_version is None:
                continue

            # Must have at least one scene to be buildable
            if not has_scenes(base_dir):
                print(f"[skip] {repo_dir.name}: no .unity scenes found")
                break

            jdk_version = pick_jdk(unity_version)

            app_entry = {
                "id": repo_dir.name,
                "path": normalize_path(base_dir),
                "unity": unity_version,
                "jdk": jdk_version,
                "has_upm": has_upm_manifest(base_dir),
            }
            break  # take first (shallowest) Unity project found

        if app_entry:
            apps.append(app_entry)
            print(f"[ok] {repo_dir.name} (Unity {app_entry['unity']}, JDK {app_entry['jdk']})")
        else:
            print(f"[skip] {repo_dir.name}: no valid Unity project found")

    manifest = {"apps": apps}

    with open(OUTPUT_FILE, "w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False, default_flow_style=False)

    print(f"\nGenerated {len(apps)} build entries.")


if __name__ == "__main__":
    analyze()
