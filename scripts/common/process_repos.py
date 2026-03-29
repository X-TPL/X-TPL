import json
import requests
from zipfile import ZipFile
from pathlib import Path


def download_repos(storage_root: str | Path):
    storage_root = Path(storage_root)
    extract_root = storage_root / "extracted"

    storage_root.mkdir(parents=True, exist_ok=True)
    extract_root.mkdir(parents=True, exist_ok=True)

    with open("repos.json") as f:
        repos = json.load(f)

    for repo in repos:
        try:
            if not repo["buildable"]:
                continue

            name = repo["full_name"].replace("/", "-")
            zip_path = storage_root / f"{name}.zip"

            print(f"[download] {repo['full_name']}")

            response = requests.get(repo["zip_url"], stream=True)
            response.raise_for_status()

            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            with ZipFile(zip_path, "r") as z:
                z.extractall(extract_root / name)

        except Exception as e:
            print(f"[error] {repo['full_name']}: {e}")
