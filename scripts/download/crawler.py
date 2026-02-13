import os
import json
from github import Github, Auth
from dotenv import load_dotenv

OUTPUT_FILE = "repos.json"

# -----------------------
# Setup GitHub
# -----------------------
load_dotenv()
token = os.getenv("TOKEN")

if not token:
    raise RuntimeError("TOKEN not set in environment")

g = Github(auth=Auth.Token(token))

# -----------------------
# Scan repositories
# -----------------------
repos_data = []

repositories = g.search_repositories(query="language:dart app")

for repo in repositories[:50]:  # adjust limit as needed
    print(f"[scan] {repo.full_name}")

    zip_url = repo.get_archive_link("zipball")

    try:
        # Efficient API call — no zip download
        repo.get_contents("pubspec.yaml")
        repo.get_contents("android")
        repo.get_contents("lib/main.dart")
        buildable = True
    except Exception:
        buildable = False

    repos_data.append({
        "full_name": repo.full_name,
        "zip_url": zip_url,
        "buildable": buildable
    })

# -----------------------
# Write output
# -----------------------
with open(OUTPUT_FILE, "w") as f:
    json.dump(repos_data, f, indent=2)

print(f"\nSaved {len(repos_data)} entries to {OUTPUT_FILE}")
