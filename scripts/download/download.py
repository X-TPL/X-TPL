import requests
import os
import re
from github import Github
from github import Auth
from dotenv import load_dotenv
from zipfile import ZipFile
from pathlib import Path
import yaml
from packaging.version import Version, InvalidVersion


def normalize_path(path: str) -> str:
    return str(Path(path).as_posix())


def create_manifest_entry(
        app_id: str,
        app_path: str,
        flutter_version: str,
        output_type: str,
):
    return {
        "id": app_id,
        "path": normalize_path(app_path),
        "flutter": flutter_version,
        "output": output_type.lower(),
    }


def write_manifest(entries, output_file):
    manifest = {"apps": entries}

    with open(output_file, "w") as f:
        yaml.safe_dump(
            manifest,
            f,
            sort_keys=False,
            default_flow_style=False,
        )


def extract_flutter_version(text: str):
    flutter_match = FLUTTER_RE.search(text)
    if flutter_match:
        return flutter_match.group(1)

    dart_match = DART_RE.search(text)
    if dart_match:
        return flutter_from_dart(dart_match.group(1))

    raise ValueError("No Flutter or Dart SDK constraint found")


def flutter_from_dart(dart_version: str) -> str:
    """
    Given a Dart SDK lower bound (e.g. '3.0.0'),
    return the minimum compatible Flutter version.
    """
    try:
        dart_v = Version(dart_version)
    except InvalidVersion as e:
        raise ValueError(f"Invalid Dart version: {dart_version}") from e

    for dart_min, flutter_min in DART_TO_FLUTTER:
        if dart_v >= Version(dart_min):
            print(f"[info] inferred Flutter {flutter_min} from Dart {dart_version}")
            return flutter_min

    raise RuntimeError(
        f"No compatible Flutter version found for Dart {dart_version}"
    )


# load env
load_dotenv()
token = os.getenv("TOKEN")
auth = Auth.Token(token)
g = Github(auth=auth)

apps = []
repositories = g.search_repositories(query='language:dart app')

for repository in repositories[:10]:  # testing
    file_path = os.path.expanduser(f"~/storage/assets/{repository.full_name.replace('/', '-')}.zip")
    zip_url = repository.get_archive_link("zipball")
    response = requests.get(zip_url)
    with open(file_path, "wb") as f:
        f.write(response.content)

for file in os.listdir("~/storage/assets"):
    file_path = Path(f"~/storage/assets/{file}")
    if Path.is_file(file_path):
        with ZipFile(file_path, 'r') as zObject:
            zObject.extractall(path='~/storage/assets/extracted')

patterns = ["pubspec.yaml", "/android", "lib/main.dart"]
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
buildable = True
unbuildable_counter = 0
for folder in os.listdir("~/storage/assets/extracted/"):
    folder_path = Path(f"~/storage/assets/extracted/{folder}")
    for pattern in patterns:
        if not folder_path.rglob(pattern):
            buildable = False
    if not buildable:
        os.remove(folder_path)
        unbuildable_counter += 1
    else:
        try:
            pubspec_path = next(
                Path(folder_path).rglob("pubspec.yaml"),
                None
            )

            if pubspec_path is None:
                raise FileNotFoundError(f"No pubspec.yaml found under {folder_path}")
            text = pubspec_path.read_text()  # we only expect 1 result, so we can cast it
            flutter_version = extract_flutter_version(text)
            apps.append(create_manifest_entry(folder, str(pubspec_path.__str__().replace("pubspec.yaml", "")),
                                              flutter_version, "apk"))
        except Exception as e:
            print(e)

write_manifest(apps, "../builder/build_manifest.yaml")
