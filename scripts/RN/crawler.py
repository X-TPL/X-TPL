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

repositories = g.search_repositories(query='("react-native" in:readme OR topic:react-native) language:JavaScript language:TypeScript ',
    sort='updated'
)
print(f"{repositories.totalCount} Repositories found in total")
for repo in repositories:
    print(f"[scan] {repo.full_name}")

    buildable = False
    commit = None
    branch_used = None

    try:
        # ---------------------------------
        # Prefer latest release if exists
        # ---------------------------------
        try:
            release = repo.get_latest_release()
            target = release.target_commitish
            print(f"[info] using release: {release.tag_name}")

            commit = repo.get_commit(target)
            branch_used = target

        except Exception:
            # No release found → fallback to default branch
            branch_used = repo.default_branch
            commit = repo.get_commit(branch_used)

        # ---------------------------------
        # Analyze repository tree
        # ---------------------------------
        tree = repo.get_git_tree(commit.sha, recursive=True)
        paths = [item.path for item in tree.tree]

        # Find all package.json locations
        package_dirs = [
            os.path.dirname(p)
            for p in paths
            if p.endswith("package.json")
        ]
        if len(package_dirs) > 0:
            buildable = True # default is false

    except Exception as e:
        print(f"[error] {repo.full_name}: {e}")

    # ---------------------------------
    # Archive URL pinned to commit SHA
    # ---------------------------------
    zip_url = None
    if commit:
        zip_url = f"https://github.com/{repo.full_name}/archive/{commit.sha}.zip"

    repos_data.append({
        "full_name": repo.full_name,
        "branch_or_tag": branch_used,
        "commit": commit.sha if commit else None,
        "zip_url": zip_url,
        "buildable": buildable,
        "topics": repo.topics,
        "fork": repo.fork
    })

# -----------------------
# Write output
# -----------------------
with open(OUTPUT_FILE, "w") as f:
    json.dump(repos_data, f, indent=2)

print(f"\nSaved {len(repos_data)} entries to {OUTPUT_FILE}")
