"""
Distribute repos from build_manifest.yaml across multiple volumes.

Usage:
    python distribute_repos.py --count 100 /mnt/vol1 /mnt/vol2 /mnt/vol3

Copies the next `count` repo source directories into each volume under <vol>/repos/.
The last volume gets any remainder. Re-run the analyzer on each volume afterward.

If there are more volumes than needed (repos run out), remaining volumes are skipped.
"""

import argparse
import shutil
import sys
import yaml
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, required=True,
                        help="Number of repos to copy per volume")
    parser.add_argument("--manifest", default=str(Path(__file__).parent / "build_manifest.yaml"),
                        help="Path to build_manifest.yaml (default: RN/build_manifest.yaml)")
    parser.add_argument("volumes", nargs="+",
                        help="Mount paths of the target volumes")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path) as f:
        all_apps = yaml.safe_load(f)["apps"]

    total = len(all_apps)
    print(f"Manifest has {total} apps, distributing {args.count} per volume across {len(args.volumes)} volume(s)")

    offset = 0
    for vol_idx, vol in enumerate(args.volumes):
        vol_path = Path(vol)
        if offset >= total:
            print(f"[vol {vol_idx+1}] No repos left to assign, skipping {vol}")
            break

        # Last volume gets whatever remains
        if vol_idx == len(args.volumes) - 1:
            batch = all_apps[offset:]
        else:
            batch = all_apps[offset: offset + args.count]

        if not batch:
            break

        repos_dir = vol_path / "repos"
        repos_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        for app in batch:
            # Walk up from the manifest path to find the top-level repo root
            # (id is always the name of that root directory)
            src = Path(app["path"])
            while src.name != app["id"] and src.parent != src:
                src = src.parent
            dst = repos_dir / app["id"]

            if dst.exists():
                print(f"  [skip] {src.name} already at destination")
                copied += 1
            elif not src.exists():
                print(f"  [warn] source missing, skipping: {src}")
            else:
                print(f"  [copy] {src.name} -> {dst}")
                shutil.copytree(src, dst)
                copied += 1

        print(f"[vol {vol_idx+1}] {vol}: {copied} repos copied")
        offset += args.count

    print("Done.")


if __name__ == "__main__":
    main()
