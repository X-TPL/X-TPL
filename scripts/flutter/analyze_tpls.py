#!/usr/bin/env python3
"""
Analyze Flutter build artifacts to produce a TPL version report.

For every pubspec.lock found under output/<app>/ (root level only, r8/ and
obfuscated/ subdirs are skipped since they are the same app), collects all
hosted/git packages and their resolved versions, then writes tpl_analysis.txt:

    package_name: 1.0.0                    (single version seen)
    package_name: {1.0.0, 2.0.0, 3.1.0}   (multiple versions seen)

Sorted alphabetically. Summary header shows total unique packages and pairs.
"""

import pathlib
from collections import defaultdict

import yaml

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
REPORT_FILE = ROOT / "tpl_analysis.txt"

# Sources that are not third-party packages (skip them)
_SKIP_SOURCES = {"sdk"}


def collect_lock_files() -> list[pathlib.Path]:
    """Return root-level pubspec.lock files, one per app directory."""
    locks = []
    if not OUTPUT_DIR.is_dir():
        return locks
    for app_dir in sorted(OUTPUT_DIR.iterdir()):
        if not app_dir.is_dir():
            continue
        lock = app_dir / "pubspec.lock"
        if lock.exists():
            locks.append(lock)
    return locks


def parse_lock(path: pathlib.Path) -> dict[str, str]:
    """Return {package: version} for all non-SDK packages in a pubspec.lock."""
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {}

    packages = (data or {}).get("packages") or {}
    result = {}
    for name, info in packages.items():
        if not isinstance(info, dict):
            continue
        if info.get("source") in _SKIP_SOURCES:
            continue
        version = str(info.get("version", "")).strip('"').strip()
        if version:
            result[name] = version
    return result


def main() -> None:
    lock_files = collect_lock_files()
    if not lock_files:
        print(f"No pubspec.lock files found under {OUTPUT_DIR}")
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
        "# Flutter TPL Analysis",
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
