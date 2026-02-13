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
    branch = repo.default_branch
    tree = repo.get_git_tree(branch, recursive=True)

    # Collect all paths
    paths = [item.path for item in tree.tree]

    # Find all pubspec locations
    pubspec_dirs = [
        os.path.dirname(p)
        for p in paths
        if p.endswith("pubspec.yaml")
    ]

    buildable = False

    for base in pubspec_dirs:
        android_dir = f"{base}/android" if base else "android"
        main_file = f"{base}/lib/main.dart" if base else "lib/main.dart"

        has_android = any(
            p == android_dir or p.startswith(android_dir + "/")
            for p in paths
        )

        has_main = main_file in paths

        if has_android and has_main:
            buildable = True
            break

except Exception as e:
    print(f"[error] {repo.full_name}: {e}")
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
