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
    # Dart 3.x
    ("3.4.0", "3.22.0"),
    ("3.3.0", "3.19.0"),
    ("3.2.0", "3.16.0"),
    ("3.1.0", "3.13.0"),
    ("3.0.0", "3.10.0"),

    # Dart 2.19–2.17
    ("2.19.0", "3.7.0"),
    ("2.18.0", "3.3.0"),
    ("2.17.0", "3.0.0"),

    # Dart 2.16–2.12
    ("2.16.0", "2.10.0"),
    ("2.15.0", "2.8.0"),
    ("2.14.0", "2.5.0"),
    ("2.13.0", "2.2.0"),
    ("2.12.0", "2.0.0"),

    # Dart 2.11–2.8
    ("2.11.0", "1.22.0"),
    ("2.10.0", "1.20.0"),
    ("2.9.0", "1.17.0"),
    ("2.8.0", "1.17.0"),
    ("2.7.0", "1.12.13+hotfix.5"),
    ("2.6.0", "1.12.13"),           
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
    """
    Determines the correct Flutter version considering BOTH:
    - sdk (Dart) constraint
    - flutter constraint

    Returns a Flutter version that satisfies both.
    """

    flutter_match = FLUTTER_RE.search(text)
    dart_match = DART_RE.search(text)

    flutter_lower = Version(flutter_match.group(1)) if flutter_match else None
    dart_lower = Version(dart_match.group(1)) if dart_match else None

    if not flutter_lower and not dart_lower:
        raise ValueError("No Flutter/Dart SDK constraint found")

    # If Dart constraint exists → compute minimum Flutter required
    flutter_required_by_dart = None
    if dart_lower:
        flutter_required_by_dart = Version(
            flutter_from_dart(str(dart_lower))
        )

    # Decision logic:
    if flutter_lower and flutter_required_by_dart:
        # return the stricter (higher) requirement
        return str(max(flutter_lower, flutter_required_by_dart))

    if flutter_lower:
        return str(flutter_lower)

    if flutter_required_by_dart:
        return str(flutter_required_by_dart)

    raise RuntimeError("Unable to determine Flutter version")



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
