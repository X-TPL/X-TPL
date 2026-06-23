#!/usr/bin/env python3
"""
Analyze MAUI build artifacts to produce a TPL version report.

For every .csproj found under output/<app>/ (root level only, r8/ subdir is
skipped since it is the same app), collects all <PackageReference> entries and
their versions, then writes tpl_analysis.txt:

    PackageName: 1.0.0                    (single version seen)
    PackageName: {1.0.0, 2.0.0, 3.1.0}   (multiple versions seen)

Sorted alphabetically. Summary header shows total unique packages and pairs.
"""

import pathlib
import xml.etree.ElementTree as ET
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
REPORT_FILE = ROOT / "tpl_analysis.txt"


def collect_csproj_files() -> list[pathlib.Path]:
    """Return root-level .csproj files, one per app directory."""
    csprojfiles = []
    if not OUTPUT_DIR.is_dir():
        return csprojfiles
    for app_dir in sorted(OUTPUT_DIR.iterdir()):
        if not app_dir.is_dir():
            continue
        found = list(app_dir.glob("*.csproj"))
        if found:
            csprojfiles.append(found[0])
    return csprojfiles


def parse_csproj(path: pathlib.Path) -> dict[str, str]:
    """Return {package: version} for all <PackageReference> entries."""
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
    csproj_files = collect_csproj_files()
    if not csproj_files:
        print(f"No .csproj files found under {OUTPUT_DIR}")
        return

    tpl_versions: dict[str, set[str]] = defaultdict(set)
    parsed = 0

    for csproj in csproj_files:
        pkgs = parse_csproj(csproj)
        if pkgs:
            parsed += 1
            for name, version in pkgs.items():
                tpl_versions[name].add(version)

    total_packages = len(tpl_versions)
    total_pairs = sum(len(v) for v in tpl_versions.values())

    lines = [
        "# MAUI TPL Analysis",
        f"# .csproj files analyzed : {parsed} / {len(csproj_files)}",
        f"# Unique packages        : {total_packages}",
        f"# Unique TPL:version     : {total_pairs}",
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
