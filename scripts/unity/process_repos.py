import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from common.process_repos import download_repos

STORAGE_ROOT = "/home/ubuntu/storage/unity_assets"

if __name__ == "__main__":
    download_repos(STORAGE_ROOT)
