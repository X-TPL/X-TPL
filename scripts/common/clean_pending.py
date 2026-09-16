"""
Delete output folders for entries still present in build_manifest.yaml.
Useful for cleaning up incomplete builds before a rerun.

Usage (run from the framework directory, e.g. scripts/RN/):
    python ../common/clean_pending.py
    python ../common/clean_pending.py --dry-run
"""

import argparse
import shutil
import sys
import yaml
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="build_manifest.yaml")
    parser.add_argument("--output", default="output")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be deleted without deleting")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    output_dir = Path(args.output)

    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path) as f:
        apps = yaml.safe_load(f)["apps"]

    to_delete = [output_dir / app["id"] for app in apps if (output_dir / app["id"]).exists()]

    print(f"Manifest entries : {len(apps)}")
    print(f"Folders to delete: {len(to_delete)}")

    if not to_delete:
        print("Nothing to delete.")
        return

    if args.dry_run:
        print("\n[dry-run] would delete:")
        for p in to_delete:
            print(f"  {p}")
        return

    for p in to_delete:
        print(f"  deleting {p}")
        shutil.rmtree(p)

    print("\nDone.")


if __name__ == "__main__":
    main()
