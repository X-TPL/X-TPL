import json
import requests
from zipfile import ZipFile
from pathlib import Path
from dotenv import load_dotenv
import os

STORAGE_ROOT = Path("/home/ubuntu/storage/rn_assets")
EXTRACT_ROOT = STORAGE_ROOT / "extracted"

STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
EXTRACT_ROOT.mkdir(parents=True, exist_ok=True)
load_dotenv()
token = os.getenv("TOKEN")

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "repo-crawler"
})

# -----------------------
# Load repo list
# -----------------------
with open("repos.json") as f:
    repos = json.load(f)

for repo in repos:
    if not repo["buildable"]:
        continue

    name = repo["full_name"].replace("/", "-")
    zip_path = STORAGE_ROOT / f"{name}.zip"

    print(f"[download] {repo['full_name']}")

    response = session.get(repo["zip_url"], stream=True, timeout=60)
    response.raise_for_status()

    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    # -----------------------
    # Extract
    # -----------------------
    with ZipFile(zip_path, "r") as z:
        extract_path = EXTRACT_ROOT / name
        z.extractall(extract_path)

