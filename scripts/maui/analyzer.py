import yaml
import os
import re
from pathlib import Path
import xml.etree.ElementTree as ET

EXTRACT_ROOT = Path("/home/ubuntu/storage/maui_assets/extracted")
OUTPUT_FILE = "build_manifest.yaml"

SKIP_DIRS = {".git", "bin", "obj", "packages", ".vs", ".idea", "TestResults"}


# -------------------------
# Utilities
# -------------------------

def normalize_path(path: Path) -> str:
    return str(path.as_posix())


def pick_jdk(dotnet_version: int) -> int:
    return 11 if dotnet_version <= 7 else 17


def extract_android_dotnet_version(target_frameworks: str) -> int | None:
    """Extract the minimum .NET major version that targets Android."""
    matches = re.findall(r"net(\d+)\.0-android", target_frameworks, re.IGNORECASE)
    if not matches:
        return None
    return min(int(v) for v in matches)


def parse_csproj(csproj_path: Path) -> tuple[bool, int | None]:
    """
    Returns (is_maui_android, dotnet_version) or (False, None).
    """
    try:
        content = csproj_path.read_text(encoding="utf-8", errors="ignore")
        root = ET.fromstring(content)
    except Exception:
        return False, None

    use_maui = False
    target_frameworks_str = ""

    for prop_group in root.iter("PropertyGroup"):
        for child in prop_group:
            tag = child.tag.lower()
            text = (child.text or "").strip()

            if tag == "usemaui" and text.lower() == "true":
                use_maui = True

            if tag in ("targetframework", "targetframeworks"):
                target_frameworks_str += ";" + text

    has_maui_package = any(
        (ref.get("Include") or "").startswith("Microsoft.Maui")
        for ref in root.iter("PackageReference")
    )

    is_maui = use_maui or has_maui_package

    if not is_maui:
        return False, None

    dotnet_version = extract_android_dotnet_version(target_frameworks_str)
    if dotnet_version is None:
        # MAUI project but no Android target
        return False, None

    return True, dotnet_version


# -------------------------
# Analyzer
# -------------------------

def analyze():
    apps = []

    for repo_dir in EXTRACT_ROOT.iterdir():
        if not repo_dir.is_dir():
            continue

        subdirs = [d for d in repo_dir.iterdir() if d.is_dir()]
        root_dir = subdirs[0] if len(subdirs) == 1 else repo_dir

        app_entry = None

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            csproj_files = [f for f in filenames if f.endswith(".csproj")]
            if not csproj_files:
                continue

            base_dir = Path(dirpath)

            for csproj_name in csproj_files:
                csproj_path = base_dir / csproj_name

                try:
                    is_maui, dotnet_version = parse_csproj(csproj_path)

                    if not is_maui or dotnet_version is None:
                        continue

                    jdk_version = pick_jdk(dotnet_version)

                    app_entry = {
                        "id": repo_dir.name,
                        "path": normalize_path(base_dir),
                        "csproj": csproj_name,
                        "dotnet": dotnet_version,
                        "jdk": jdk_version,
                    }
                    break

                except Exception as e:
                    print(f"[skip] {repo_dir.name}/{csproj_name}: {e}")
                    continue

            if app_entry:
                break

        if app_entry:
            apps.append(app_entry)
            print(f"[ok] {repo_dir.name} (net{app_entry['dotnet']}.0-android, JDK {app_entry['jdk']})")
        else:
            print(f"[skip] {repo_dir.name}: no valid MAUI Android app found")

    manifest = {"apps": apps}

    with open(OUTPUT_FILE, "w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False, default_flow_style=False)

    print(f"\nGenerated {len(apps)} build entries.")


if __name__ == "__main__":
    analyze()
