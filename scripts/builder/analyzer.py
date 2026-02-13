import re
import yaml
from pathlib import Path
from packaging.version import Version


EXTRACT_ROOT = Path("/home/ubuntu/storage/assets/extracted")
OUTPUT_FILE = "build_manifest.yaml"

FLUTTER_RE = re.compile(
    r'flutter:\s*[\'"]?\s*>=\s*([0-9]+(?:\.[0-9]+){1,2})',
    re.IGNORECASE
)

DART_RE = re.compile(
    r'sdk:\s*[\'"]?\s*>=\s*([0-9]+(?:\.[0-9]+){1,2})',
    re.IGNORECASE
)

DART_TO_FLUTTER = [
    ("3.3.0", "3.19.0"),
    ("3.2.0", "3.16.0"),
    ("3.1.0", "3.13.0"),
    ("3.0.0", "3.10.0"),
    ("2.17.0", "3.0.0"),
    ("2.16.0", "2.10.0"),
    ("2.15.0", "2.8.0"),
    ("2.14.0", "2.5.0"),
    ("2.13.0", "2.2.0"),
    ("2.12.0", "2.0.0"),
    ("2.10.0", "1.25.0"),
    ("2.9.0", "1.22.0"),
]


# -------------------------
# Utilities
# -------------------------

def normalize_path(path: Path) -> str:
    return str(path.as_posix())


def flutter_from_dart(dart_version: str) -> str:
    dart_v = Version(dart_version)

    for dart_min, flutter_min in DART_TO_FLUTTER:
        if dart_v >= Version(dart_min):
            return flutter_min

    raise RuntimeError(f"No compatible Flutter version for Dart {dart_version}")


def extract_flutter_version(text: str) -> str:
    flutter_match = FLUTTER_RE.search(text)
    if flutter_match:
        return flutter_match.group(1)

    dart_match = DART_RE.search(text)
    if dart_match:
        return flutter_from_dart(dart_match.group(1))

    raise ValueError("No Flutter/Dart SDK constraint found")


# -------------------------
# Analyzer
# -------------------------

def analyze():
    apps = []

    for repo_dir in EXTRACT_ROOT.iterdir():
        if not repo_dir.is_dir():
            continue

        pubspecs = list(repo_dir.rglob("pubspec.yaml"))

        for pubspec_path in pubspecs:
            base_dir = pubspec_path.parent

            # Only consider valid Flutter app roots
            android_dir = base_dir / "android"
            main_file = base_dir / "lib" / "main.dart"

            if not android_dir.exists() or not main_file.exists():
                # Skip packages/examples
                continue

            try:
                text = pubspec_path.read_text()
                flutter_version = extract_flutter_version(text)

                app_entry = {
                    "id": repo_dir.name,
                    "path": normalize_path(base_dir),
                    "flutter": flutter_version,
                    "output": "apk"
                }

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
