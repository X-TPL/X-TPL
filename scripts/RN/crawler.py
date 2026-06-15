import os
import json
from datetime import datetime, timedelta, timezone
from github import Github, Auth
from dotenv import load_dotenv

OUTPUT_FILE = "repos.json"
TARGET_BUILDABLE = 100000
BATCH_SIZE = 1000

# -----------------------
# Setup GitHub
# -----------------------
load_dotenv()
token = os.getenv("TOKEN")

if not token:
    raise RuntimeError("TOKEN not set in environment")

g = Github(auth=Auth.Token(token))

# -----------------------
# Helpers
# -----------------------

def is_buildable(repo, commit):
    try:
        tree = repo.get_git_tree(commit.sha, recursive=True)
        paths = [item.path for item in tree.tree]

        # Must have at least one package.json
        return any(p.endswith("package.json") for p in paths)
    except Exception:
        return False


def get_commit_and_branch(repo):
    try:
        release = repo.get_latest_release()
        target = release.target_commitish
        print(f"[info] using release: {release.tag_name}")
        commit = repo.get_commit(target)
        return commit, target
    except Exception:
        branch = repo.default_branch
        commit = repo.get_commit(branch)
        return commit, branch


# -----------------------
# Crawl
# -----------------------

repos_data = []
buildable_count = 0
cursor_time = datetime.now(timezone.utc)
seen = set()

while buildable_count < TARGET_BUILDABLE:
    query_time = cursor_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    query = f"topic:react-native language:TypeScript pushed:<{query_time}"

    print(f"\n[query] {query}")

    results = g.search_repositories(
        query=query,
        sort="updated",
        order="desc"
    )

    batch_count = 0
    oldest_in_batch = None

    for repo in results:
        if repo.full_name in seen:
            continue

        seen.add(repo.full_name)
        batch_count += 1

        print(f"[scan] {repo.full_name}")

        try:
            commit, branch_used = get_commit_and_branch(repo)
            buildable = is_buildable(repo, commit)

            if buildable:
                buildable_count += 1
                print(f"[ok] buildable ({buildable_count}/{TARGET_BUILDABLE})")

            repos_data.append({
                "full_name": repo.full_name,
                "branch_or_tag": branch_used,
                "commit": commit.sha if commit else None,
                "zip_url": f"https://github.com/{repo.full_name}/archive/{commit.sha}.zip" if commit else None,
                "buildable": buildable,
                "topics": repo.topics,
                "fork": repo.fork
            })

            repo_time = repo.pushed_at
            if oldest_in_batch is None or repo_time < oldest_in_batch:
                oldest_in_batch = repo_time

        except Exception as e:
            print(f"[error] {repo.full_name}: {e}")

        if buildable_count >= TARGET_BUILDABLE:
            break

        if batch_count >= BATCH_SIZE:
            break

    if not oldest_in_batch:
        print("[stop] no more results")
        break

    cursor_time = oldest_in_batch - timedelta(seconds=1)

# -----------------------
# Write output
# -----------------------
with open(OUTPUT_FILE, "w") as f:
    json.dump(repos_data, f, indent=2)

print(f"\nSaved {len(repos_data)} entries to {OUTPUT_FILE}")
print(f"Collected {buildable_count} buildable repos")
