#!/usr/bin/env python3
"""
Analyze Cordova build artifacts to produce a TPL version report.

package-lock.json v2/v3 stores the direct deps in the root entry:
  packages[""]["dependencies"]    -> direct runtime deps
  packages[""]["devDependencies"] -> direct dev deps
All other entries under node_modules/ are direct or transitive; those not
listed in the root entry's deps are transitive.

lockfileVersion 1 does not carry this information, so packages from v1 lock
files are recorded in [all] only (no direct/transitive split).

Writes tpl_analysis.txt with three sections:

    [direct]
    package-name: 1.0.0

    [transitive]
    package-name: 1.0.0

    [all]
    package-name: {1.0.0, 2.0.0}

Each section is sorted alphabetically. Summary header shows counts per section.
Supports lockfileVersion 1, 2, and 3.
"""

import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
REPORT_FILE = ROOT / "tpl_analysis.txt"


def collect_lock_files() -> list[pathlib.Path]:
    if not OUTPUT_DIR.is_dir():
        return []
    locks = []
    for app_dir in sorted(OUTPUT_DIR.iterdir()):
        if not app_dir.is_dir():
            continue
        lock = app_dir / "package-lock.json"
        if lock.exists():
            locks.append(lock)
    return locks


def parse_lock(path: pathlib.Path) -> tuple[dict[str, str], dict[str, str], bool]:
    """
    Return (direct, transitive, has_split).
    has_split is False for v1 lock files where the distinction is unavailable.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}, False

    lockfile_version = (data or {}).get("lockfileVersion", 1)

    if lockfile_version >= 2:
        root_entry = (data.get("packages") or {}).get("", {})
        direct_names: set[str] = set()
        for section in ("dependencies", "devDependencies"):
            block = root_entry.get(section) or {}
            if isinstance(block, dict):
                direct_names.update(block.keys())

        direct: dict[str, str] = {}
        transitive: dict[str, str] = {}
        for pkg_path, info in (data.get("packages") or {}).items():
            if not pkg_path:
                continue
            if not isinstance(info, dict):
                continue
            parts = pkg_path.split("node_modules/")
            name = parts[-1].rstrip("/")
            version = str(info.get("version", "")).strip()
            if not name or not version:
                continue
            if name in direct_names:
                direct[name] = version
            else:
                transitive[name] = version
        return direct, transitive, True

    else:
        # v1: no direct/transitive distinction available
        all_pkgs: dict[str, str] = {}
        for name, info in (data.get("dependencies") or {}).items():
            if not isinstance(info, dict):
                continue
            version = str(info.get("version", "")).strip()
            if version:
                all_pkgs[name] = version
        return all_pkgs, {}, False


def main() -> None:
    lock_files = collect_lock_files()
    if not lock_files:
        print(f"No package-lock.json files found under {OUTPUT_DIR}")
        return

    direct_versions: dict[str, set[str]] = defaultdict(set)
    transitive_versions: dict[str, set[str]] = defaultdict(set)
    all_versions: dict[str, set[str]] = defaultdict(set)
    parsed = 0
    v1_count = 0

    for lock in lock_files:
        direct, transitive, has_split = parse_lock(lock)
        if direct or transitive:
            parsed += 1
        if not has_split:
            v1_count += 1
        for name, version in direct.items():
            direct_versions[name].add(version)
            all_versions[name].add(version)
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
        "# Cordova TPL Analysis",
        f"# Lock files analyzed : {parsed} / {len(lock_files)}",
        *(
            [f"# (v1 lock files, no direct/transitive split): {v1_count}"]
            if v1_count
            else []
        ),
        f"# Direct   packages   : {d_pkgs}  ({d_pairs} TPL:version pairs)",
        f"# Transitive packages : {t_pkgs}  ({t_pairs} TPL:version pairs)",
        f"# All packages        : {a_pkgs}  ({a_pairs} TPL:version pairs)",
        "",
    ]

    lines = (
        header
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
