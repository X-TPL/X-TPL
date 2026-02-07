import subprocess
from zipfile import ZipFile
import os
from pathlib import Path
import re

for file in os.listdir("../assets"):
    file_path = Path(f"../assets/{file}")
    if Path.is_file(file_path):
        with ZipFile(file_path, 'r') as zObject:
            zObject.extractall(path='../assets/extracted')

patterns = ["pubspec.yaml", "/android", "lib/main.dart"]

buildable = True
unbuildable_counter = 0
for folder in os.listdir("../assets/extracted/"):
    folder_path = Path(f"../assets/extracted/{folder}")
    for pattern in patterns:
        if not folder_path.rglob(pattern):
            buildable = False
    if not buildable:
        os.remove(folder_path)
        unbuildable_counter += 1
    else:
        pubspec_path = list(Path(folder_path).rglob("pubspec.yaml"))[
            0]
        text = pubspec_path.read_text()  # we only expect 1 result, so we can cast it
        match = re.search(r'flutter:\s*">=\s*([0-9]+(?:\.[0-9]+)*)', text)  # finds the lower bound of flutter version specified
        if match:
            flutter_version = match.group(1)
            print(flutter_version)
            result = subprocess.run(
                ["fvm", "install", flutter_version],
                capture_output=True,
                text=True,
                shell=True,
                encoding="utf-8",
                errors="replace",
            )

            print(result.stdout)
            print(result.stderr)
            print(f'cd {pubspec_path.__str__().replace("pubspec.yaml", "")} && fvm use {flutter_version}')
            subprocess.run(
                    f'cd {pubspec_path.__str__().replace("pubspec.yaml", "")} ',
                    capture_output=True,
                    text=True,
                    shell=True,
                    encoding="utf-8",
                    errors="replace",
                )
            result = subprocess.run(
                f'fvm use {flutter_version}',
                capture_output=True,
                text=True,
                shell=True,
                encoding="utf-8",
                errors="replace",
            )

            print(result.stdout)
            print(result.stderr)
            result = subprocess.run(
                f'cd ../assets/extracted/{folder} && fvm flutter pub get',
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            print(result.stdout)
            print(result.stderr)
            print(f"cd ../assets/extracted/{folder} && fvm flutter build apk --debug")
        else:
            Exception("couldnt find flutter version from pubspec.yaml ", folder)
