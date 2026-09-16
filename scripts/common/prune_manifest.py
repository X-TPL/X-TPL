"""
Remove already-processed entries from build_manifest.yaml.

An entry is considered processed if its output folder exists.

Usage (run from the framework directory, e.g. scripts/RN/):
    python ../common/prune_manifest.py
    python ../common/prune_manifest.py --manifest build_manifest.yaml --output output/
    python ../common/prune_manifest.py --dry-run
"""

import argparse
import sys
import yaml
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="build_manifest.yaml",
                        help="Path to build_manifest.yaml (default: ./build_manifest.yaml)")
    parser.add_argument("--output", default="output",
                        help="Path to output directory (default: ./output)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be removed without modifying the file")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    output_dir = Path(args.output)

    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path) as f:
        data = yaml.safe_load(f)

    apps = data["apps"]
    total = len(apps)

    remaining = []
    removed = []

    for app in apps:
        app_id = app["id"]
        if (output_dir / app_id).exists():
            removed.append(app_id)
        else:
            remaining.append(app)

    print(f"Total entries : {total}")
    print(f"Already built : {len(removed)}")
    print(f"Remaining     : {len(remaining)}")

    if args.dry_run:
        print("\n[dry-run] would remove:")
        for app_id in removed:
            print(f"  {app_id}")
        return

    with open(manifest_path, "w") as f:
        yaml.safe_dump({"apps": remaining}, f, sort_keys=False, default_flow_style=False)

    print(f"\nManifest updated: {manifest_path}")


if __name__ == "__main__":
    main()
