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


def generate_chart(usage: dict[str, int], total: int, title: str, output_path: pathlib.Path, n: int = 20) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping chart (pip install matplotlib)")
        return
    if not usage or total == 0:
        return

    top = sorted(usage.items(), key=lambda x: x[1], reverse=True)[:n]
    names = [name for name, _ in reversed(top)]
    pcts = [count / total * 100 for _, count in reversed(top)]

    fig, ax = plt.subplots(figsize=(10, max(4, len(top) * 0.45)))
    bars = ax.barh(names, pcts, color="#4878CF", edgecolor="white", height=0.7)

    for bar, pct in zip(bars, pcts):
        ax.text(
            bar.get_width() + 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{pct:.1f}%",
            va="center", ha="left", fontsize=9,
        )

    ax.set_xlabel("Percentage of repositories (%)", fontsize=11)
    ax.set_title(title, fontsize=13, pad=12)
    ax.set_xlim(0, min(100, max(pcts) * 1.15))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="y", labelsize=9)
    ax.tick_params(axis="x", labelsize=9)

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Chart saved to {output_path}")


def histogram_lines(title: str, usage: dict[str, int], total: int, n: int = 20) -> list[str]:
    top = sorted(usage.items(), key=lambda x: x[1], reverse=True)[:n]
    if not top:
        return [f"[{title}]", "(no data)"]
    max_count = top[0][1]
    max_name_len = max(len(name) for name, _ in top)
    bar_width = 40
    lines = [f"[{title}]"]
    for name, count in top:
        pct = count / total * 100 if total else 0
        filled = round(bar_width * count / max_count)
        lines.append(f"{name:<{max_name_len}}  {'█' * filled:<{bar_width}}  {pct:5.1f}%  ({count})")
    return lines


def main() -> None:
    app_dirs = collect_app_dirs()
    if not app_dirs:
        print(f"No app directories found under {OUTPUT_DIR}")
        return

    direct_versions: dict[str, set[str]] = defaultdict(set)
    transitive_versions: dict[str, set[str]] = defaultdict(set)
    all_versions: dict[str, set[str]] = defaultdict(set)
    app_usage: dict[str, int] = defaultdict(int)

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
                app_usage[name] += 1
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
                app_usage[name] += 1

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

    total_parsed = lock_parsed + csproj_parsed
    top10 = sorted(app_usage.items(), key=lambda x: x[1], reverse=True)[:10]
    top10_lines = ["[top 10 by repository count]"]
    for rank, (name, count) in enumerate(top10, 1):
        pct = count / total_parsed * 100 if total_parsed else 0
        top10_lines.append(f"{rank:>2}. {name}  —  {count} repos ({pct:.1f}%)")

    lines = (
        header
        + top10_lines
        + [""]
        + histogram_lines("histogram - top 20 direct deps", app_usage, total_parsed)
        + [""]
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
    generate_chart(
        app_usage, total_parsed,
        "Top 20 Most Used MAUI Libraries (Direct Dependencies)",
        ROOT / "tpl_chart.pdf",
    )


if __name__ == "__main__":
    main()
