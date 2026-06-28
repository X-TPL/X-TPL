#!/usr/bin/env python3
"""
Analyze Flutter build artifacts to produce a TPL version report.

pubspec.lock already encodes the direct/transitive distinction via the
`dependency` field on each entry:
  "direct main"  -> listed in dependencies:
  "direct dev"   -> listed in dev_dependencies:
  "transitive"   -> pulled in by another package

For every pubspec.lock found under output/<app>/ (root level only, r8/ and
obfuscated/ subdirs are skipped), writes tpl_analysis.txt with three sections:

    [direct]
    package_name: 1.0.0

    [transitive]
    package_name: 1.0.0

    [all]
    package_name: {1.0.0, 2.0.0}

Each section is sorted alphabetically. Summary header shows counts per section.
"""

import pathlib
from collections import defaultdict

import yaml

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
REPORT_FILE = ROOT / "tpl_analysis.txt"

_SKIP_SOURCES = {"sdk"}


def collect_lock_files() -> list[pathlib.Path]:
    if not OUTPUT_DIR.is_dir():
        return []
    locks = []
    for app_dir in sorted(OUTPUT_DIR.iterdir()):
        if not app_dir.is_dir():
            continue
        lock = app_dir / "pubspec.lock"
        if lock.exists():
            locks.append(lock)
    return locks


def parse_lock(path: pathlib.Path) -> tuple[dict[str, str], dict[str, str]]:
    """Return (direct, transitive) dicts of {package: version}."""
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {}, {}

    packages = (data or {}).get("packages") or {}
    direct: dict[str, str] = {}
    transitive: dict[str, str] = {}

    for name, info in packages.items():
        if not isinstance(info, dict):
            continue
        if info.get("source") in _SKIP_SOURCES:
            continue
        version = str(info.get("version", "")).strip('"').strip()
        if not version:
            continue
        dep_kind = info.get("dependency", "")
        if dep_kind.startswith("direct"):
            direct[name] = version
        else:
            transitive[name] = version

    return direct, transitive


def main() -> None:
    lock_files = collect_lock_files()
    if not lock_files:
        print(f"No pubspec.lock files found under {OUTPUT_DIR}")
        return

    direct_versions: dict[str, set[str]] = defaultdict(set)
    transitive_versions: dict[str, set[str]] = defaultdict(set)
    all_versions: dict[str, set[str]] = defaultdict(set)
    app_usage: dict[str, int] = defaultdict(int)
    parsed = 0

    for lock in lock_files:
        direct, transitive = parse_lock(lock)
        if direct or transitive:
            parsed += 1
        for name, version in direct.items():
            direct_versions[name].add(version)
            all_versions[name].add(version)
            app_usage[name] += 1
        for name, version in transitive.items():
            transitive_versions[name].add(version)
            all_versions[name].add(version)

    def section_lines(title: str, data: dict[str, set[str]]) -> list[str]:
        lines = [f"[{title}]"]
        for name in sorted(data):
            versions = sorted(data[name])
            if len(versions) == 1:
                lines.append(f"{name}: {versions[0]}")
            else:
                lines.append(f"{name}: {{{', '.join(versions)}}}")
        return lines

    d_pkgs = len(direct_versions)
    d_pairs = sum(len(v) for v in direct_versions.values())
    t_pkgs = len(transitive_versions)
    t_pairs = sum(len(v) for v in transitive_versions.values())
    a_pkgs = len(all_versions)
    a_pairs = sum(len(v) for v in all_versions.values())

    header = [
        "# Flutter TPL Analysis",
        f"# Lock files analyzed : {parsed} / {len(lock_files)}",
        f"# Direct   packages   : {d_pkgs}  ({d_pairs} TPL:version pairs)",
        f"# Transitive packages : {t_pkgs}  ({t_pairs} TPL:version pairs)",
        f"# All packages        : {a_pkgs}  ({a_pairs} TPL:version pairs)",
        "",
    ]

    top10 = sorted(app_usage.items(), key=lambda x: x[1], reverse=True)[:10]
    top10_lines = ["[top 10 by repository count]"]
    for rank, (name, count) in enumerate(top10, 1):
        pct = count / parsed * 100 if parsed else 0
        top10_lines.append(f"{rank:>2}. {name}  —  {count} repos ({pct:.1f}%)")

    lines = (
        header
        + top10_lines
        + [""]
        + section_lines("direct", direct_versions)
        + [""]
        + section_lines("transitive", transitive_versions)
        + [""]
        + section_lines("all", all_versions)
        + [""]
    )

    report = "\n".join(lines)
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(
        f"Written to {REPORT_FILE}  "
        f"(direct: {d_pkgs}, transitive: {t_pkgs}, all: {a_pkgs})"
    )


if __name__ == "__main__":
    main()
