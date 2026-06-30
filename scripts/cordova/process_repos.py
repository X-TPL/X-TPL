import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from common.process_repos import download_repos

load_dotenv()
STORAGE_ROOT = os.getenv("STORAGE_ROOT_CORDOVA")
if not STORAGE_ROOT:
    raise RuntimeError("STORAGE_ROOT_CORDOVA not set in environment")

if __name__ == "__main__":
    download_repos(STORAGE_ROOT)
