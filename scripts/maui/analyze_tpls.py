#!/usr/bin/env python3
"""
Analyze MAUI build artifacts to produce a TPL version report.

Per app directory, tries in order:

  packages.lock.json  (preferred — direct + transitive)
    NuGet lock file generated with /p:RestorePackagesWithLockFile=true.
    Each entry has a "type" field: "Direct", "Transitive", or "CentralTransitive".
    Merged across all target frameworks in the file.

  .csproj  (fallback — direct only)
    Always present. Contains <PackageReference> entries which are direct deps only.
    Used when packages.lock.json is not available.

Writes tpl_analysis.txt with three sections:

    [direct]
    PackageName: 1.0.0

    [transitive]
    PackageName: 1.0.0

    [all]
    PackageName: {1.0.0, 2.0.0}

Each section is sorted alphabetically. Summary header shows counts per section.
"""

import json
import pathlib
import xml.etree.ElementTree as ET
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
REPORT_FILE = ROOT / "tpl_analysis.txt"


def collect_app_dirs() -> list[pathlib.Path]:
    if not OUTPUT_DIR.is_dir():
        return []
    return sorted(d for d in OUTPUT_DIR.iterdir() if d.is_dir())


def parse_packages_lock(path: pathlib.Path) -> tuple[dict[str, str], dict[str, str]]:
    """Return (direct, transitive) from packages.lock.json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}

    direct: dict[str, str] = {}
    transitive: dict[str, str] = {}

    for _framework, packages in (data.get("dependencies") or {}).items():
        if not isinstance(packages, dict):
            continue
        for name, info in packages.items():
            if not isinstance(info, dict):
                continue
            version = str(info.get("resolved", "")).strip()
            if not version:
                continue
            if info.get("type") == "Direct":
                direct[name] = version
            else:  # Transitive or CentralTransitive
                transitive[name] = version

    return direct, transitive


def parse_csproj(path: pathlib.Path) -> dict[str, str]:
    """Return {package: version} for all <PackageReference> entries (direct only)."""
    try:
        tree = ET.parse(path)
    except Exception:
        return {}

    result = {}
    for ref in tree.iter("PackageReference"):
        name = ref.get("Include") or ref.get("Update")
        if not name:
            continue
        version = ref.get("Version") or ref.get("version")
        if version is None:
            version_el = ref.find("Version")
            if version_el is not None:
                version = version_el.text
        version = (version or "").strip()
        if version:
            result[name] = version
    return result


def main() -> None:
    app_dirs = collect_app_dirs()
    if not app_dirs:
        print(f"No app directories found under {OUTPUT_DIR}")
        return

    direct_versions: dict[str, set[str]] = defaultdict(set)
    transitive_versions: dict[str, set[str]] = defaultdict(set)
    all_versions: dict[str, set[str]] = defaultdict(set)

    lock_parsed = 0
    csproj_parsed = 0
    csproj_fallback = 0

    for app_dir in app_dirs:
        lock_path = app_dir / "packages.lock.json"
        csproj_paths = list(app_dir.glob("*.csproj"))

        if lock_path.exists():
            direct, transitive = parse_packages_lock(lock_path)
            if direct or transitive:
                lock_parsed += 1
            for name, version in direct.items():
                direct_versions[name].add(version)
                all_versions[name].add(version)
            for name, version in transitive.items():
                transitive_versions[name].add(version)
                all_versions[name].add(version)

        elif csproj_paths:
            pkgs = parse_csproj(csproj_paths[0])
            if pkgs:
                csproj_parsed += 1
                csproj_fallback += 1
            for name, version in pkgs.items():
                direct_versions[name].add(version)
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
        "# MAUI TPL Analysis",
        f"# App directories              : {len(app_dirs)}",
        f"# packages.lock.json analyzed  : {lock_parsed}",
        f"# .csproj fallback (no lock)   : {csproj_fallback}  (direct only)",
        f"# Direct   packages            : {d_pkgs}  ({d_pairs} TPL:version pairs)",
        f"# Transitive packages          : {t_pkgs}  ({t_pairs} TPL:version pairs)",
        f"# All packages                 : {a_pkgs}  ({a_pairs} TPL:version pairs)",
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

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"Written to {REPORT_FILE}  "
        f"(direct: {d_pkgs}, transitive: {t_pkgs}, all: {a_pkgs})"
    )


if __name__ == "__main__":
    main()
