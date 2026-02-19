import re
import yaml
from pathlib import Path
from packaging.version import Version


EXTRACT_ROOT = Path("/home/ubuntu/storage/assets/extracted")
OUTPUT_FILE = "build_manifest.yaml"

FLUTTER_RANGE_RE = re.compile(
    r'flutter:\s*[\'"]?\s*>=\s*([0-9]+(?:\.[0-9]+){1,2})'
    r'(?:\s*<\s*([0-9]+(?:\.[0-9]+){1,2}))?',
    re.IGNORECASE
)

DART_RANGE_RE = re.compile(
    r'sdk:\s*[\'"]?\s*>=\s*([0-9]+(?:\.[0-9]+){1,2})\s*<\s*([0-9]+(?:\.[0-9]+){1,2})',
    re.IGNORECASE
)

DART_TO_FLUTTER = [
    # Dart 3.x
    ("3.11.0", "3.41.0"),
    ("3.10.0", "3.38.0"),
    ("3.9.0", "3.35.0"),
    ("3.8.0", "3.32.0"),
    ("3.7.0", "3.29.0"),
    ("3.6.0", "3.26.0"),
    ("3.5.0", "3.24.0"),
    ("3.4.0", "3.22.0"),
    ("3.3.0", "3.19.0"),
    ("3.2.0", "3.16.0"),
    ("3.1.0", "3.13.0"),
    ("3.0.0", "3.13.0"), # manual change from 3.10

    # Dart 2.19–2.17
    ("2.19.0", "3.7.0"),
    ("2.18.0", "3.7.0"), # manual adjusted from 3.3
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

    # Convert mapping to Version objects
    mappings = [
        (Version(dart_min), flutter_min)
        for dart_min, flutter_min in DART_TO_FLUTTER
    ]

    # Sort ascending (oldest → newest)
    mappings.sort(key=lambda x: x[0])

    # Find first Dart version that is >= detected version (round UP)
    for dart_min, flutter_min in mappings:
        if dart_v <= dart_min:
            return flutter_min

    # If higher than everything we know → use latest available
    return mappings[-1][1]

def flutter_from_dart_upper_bound(upper_bound: Version) -> str:
    """
    Pick the highest Dart version we know that is still
    strictly below the upper bound constraint.
    """

    mappings = [
        (Version(dart_min), flutter_min)
        for dart_min, flutter_min in DART_TO_FLUTTER
    ]

    # sort ascending
    mappings.sort(key=lambda x: x[0])

    best_match = None

    for dart_min, flutter_min in mappings:
        if dart_min < upper_bound:
            best_match = flutter_min
        else:
            break

    if best_match:
        return best_match

    raise RuntimeError(
        f"No Dart mapping satisfies upper bound < {upper_bound}"
    )

def extract_flutter_version(text: str) -> str:
    """
    Determines the correct Flutter version considering:
    - Dart upper bound (preferred strategy)
    - Flutter lower and upper bounds
    """

    flutter_match = FLUTTER_RANGE_RE.search(text)
    dart_match = DART_RANGE_RE.search(text)

    flutter_lower = None
    flutter_upper = None

    if flutter_match:
        flutter_lower = Version(flutter_match.group(1))
        if flutter_match.group(2):
            flutter_upper = Version(flutter_match.group(2))

    dart_upper = None
    if dart_match:
        dart_upper = Version(dart_match.group(2))

    if not flutter_match and not dart_match:
        raise ValueError("No Flutter/Dart SDK constraint found")

    # -----------------------------
    # Step 1: Pick from Dart upper bound
    # -----------------------------
    flutter_required_by_dart = None

    if dart_upper:
        candidate = Version(
            flutter_from_dart_upper_bound(dart_upper)
        )
        flutter_required_by_dart = candidate

    # -----------------------------
    # Step 2: Apply Flutter constraints
    # -----------------------------
    candidates = []

    if flutter_required_by_dart:
        candidates.append(flutter_required_by_dart)

    if flutter_lower:
        candidates.append(flutter_lower)

    if not candidates:
        raise RuntimeError("Unable to determine Flutter version")

    selected = max(candidates)

    # Enforce flutter upper bound if present
    if flutter_upper and selected >= flutter_upper:
        # choose nearest version below upper bound
        mappings = sorted(
            [Version(f) for _, f in DART_TO_FLUTTER]
        )
        valid = [v for v in mappings if v < flutter_upper]
        if not valid:
            raise RuntimeError(
                f"No Flutter version satisfies < {flutter_upper}"
            )
        selected = valid[-1]

    return str(selected)



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
