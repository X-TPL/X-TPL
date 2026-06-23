#!/usr/bin/env python3
"""
Analyze Cordova build artifacts to produce a TPL version report.

For every package-lock.json found under output/<app>/ (root level only, r8/
subdir is skipped since it is the same app), collects all npm packages and
their resolved versions, then writes tpl_analysis.txt:

    package-name: 1.0.0                    (single version seen)
    package-name: {1.0.0, 2.0.0, 3.1.0}   (multiple versions seen)

Sorted alphabetically. Summary header shows total unique packages and pairs.
Supports lockfileVersion 1, 2, and 3.
"""

import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
REPORT_FILE = ROOT / "tpl_analysis.txt"


def collect_lock_files() -> list[pathlib.Path]:
    """Return root-level package-lock.json files, one per app directory."""
    locks = []
    if not OUTPUT_DIR.is_dir():
        return locks
    for app_dir in sorted(OUTPUT_DIR.iterdir()):
        if not app_dir.is_dir():
            continue
        lock = app_dir / "package-lock.json"
        if lock.exists():
            locks.append(lock)
    return locks


def parse_lock(path: pathlib.Path) -> dict[str, str]:
    """Return {package: version} for all packages in a package-lock.json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    result = {}
    lockfile_version = (data or {}).get("lockfileVersion", 1)

    if lockfile_version >= 2:
        for pkg_path, info in (data.get("packages") or {}).items():
            if not pkg_path:  # skip root package
                continue
            if not isinstance(info, dict):
                continue
            # extract name from paths like "node_modules/foo" or
            # "node_modules/@scope/foo/node_modules/bar"
            parts = pkg_path.split("node_modules/")
            name = parts[-1].rstrip("/")
            version = str(info.get("version", "")).strip()
            if name and version:
                result[name] = version
    else:
        for name, info in (data.get("dependencies") or {}).items():
            if not isinstance(info, dict):
                continue
            version = str(info.get("version", "")).strip()
            if version:
                result[name] = version

    return result


def main() -> None:
    lock_files = collect_lock_files()
    if not lock_files:
        print(f"No package-lock.json files found under {OUTPUT_DIR}")
        return

    tpl_versions: dict[str, set[str]] = defaultdict(set)
    parsed = 0

    for lock in lock_files:
        pkgs = parse_lock(lock)
        if pkgs:
            parsed += 1
            for name, version in pkgs.items():
                tpl_versions[name].add(version)

    total_packages = len(tpl_versions)
    total_pairs = sum(len(v) for v in tpl_versions.values())

    lines = [
        "# Cordova TPL Analysis",
        f"# Lock files analyzed : {parsed} / {len(lock_files)}",
        f"# Unique packages     : {total_packages}",
        f"# Unique TPL:version  : {total_pairs}",
        "",
    ]

    for name in sorted(tpl_versions):
        versions = sorted(tpl_versions[name])
        if len(versions) == 1:
            lines.append(f"{name}: {versions[0]}")
        else:
            lines.append(f"{name}: {{{', '.join(versions)}}}")

    report = "\n".join(lines) + "\n"
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"Written to {REPORT_FILE}  ({total_packages} packages, {total_pairs} TPL:version pairs)")


if __name__ == "__main__":
    main()
