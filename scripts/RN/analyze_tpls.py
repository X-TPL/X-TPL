#!/usr/bin/env python3
"""
Analyze React Native build artifacts to produce a TPL version report.

Supports two lock file formats, tried in order per app directory:

  package-lock.json (npm)
    v2/v3: direct deps read from packages[""] root entry — no extra file needed.
    v1:    no direct/transitive split available; all packages go to [all] only.

  yarn.lock (yarn classic v1 and berry v2+)
    yarn.lock carries no direct/transitive metadata, so package.json is used
    for the split when present. If package.json is missing, all packages go
    to [all] only.

Writes tpl_analysis.txt with three sections:

    [direct]
    package-name: 1.0.0

    [transitive]
    package-name: 1.0.0

    [all]
    package-name: {1.0.0, 2.0.0}

Each section is sorted alphabetically. Summary header shows counts per section.
"""

import json
import pathlib
import re
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
REPORT_FILE = ROOT / "tpl_analysis.txt"


def collect_app_dirs() -> list[pathlib.Path]:
    if not OUTPUT_DIR.is_dir():
        return []
    return sorted(d for d in OUTPUT_DIR.iterdir() if d.is_dir())


# ---------- npm ----------

def parse_npm_lock(path: pathlib.Path) -> tuple[dict[str, str], dict[str, str], bool]:
    """
    Return (direct, transitive, has_split).
    has_split is False for v1 where the distinction is unavailable.
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
        all_pkgs: dict[str, str] = {}
        for name, info in (data.get("dependencies") or {}).items():
            if not isinstance(info, dict):
                continue
            version = str(info.get("version", "")).strip()
            if version:
                all_pkgs[name] = version
        return all_pkgs, {}, False


# ---------- yarn ----------

_YARN_SPEC_RE = re.compile(r'^(@[^@/]+/[^@]+|[^@]+)@')


def _extract_name(spec: str) -> str | None:
    """Extract package name from a yarn specifier like pkg@^1.0 or @scope/pkg@^1.0."""
    m = _YARN_SPEC_RE.match(spec.strip().strip('"'))
    return m.group(1) if m else None


def parse_yarn_lock(path: pathlib.Path) -> dict[str, str]:
    """Return {package: version} for all packages in a yarn.lock (v1 or berry)."""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return {}

    is_berry = "__metadata:" in content[:500]
    result: dict[str, str] = {}
    current_names: list[str] = []

    for line in content.splitlines():
        # Top-level line (not indented)
        if not line.startswith((" ", "\t")):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped in ("__metadata:", "---"):
                current_names = []
                continue
            if stripped.endswith(":"):
                # One or more comma-separated specifiers
                raw = stripped.rstrip(":")
                current_names = []
                for spec in raw.split(","):
                    name = _extract_name(spec)
                    if name:
                        current_names.append(name)

        # Indented version line
        elif current_names:
            stripped = line.strip()
            version: str | None = None
            if is_berry:
                m = re.match(r'^version:\s+["\']?([^\s"\']+)["\']?$', stripped)
                if m:
                    version = m.group(1)
            else:
                m = re.match(r'^version\s+"([^"]+)"$', stripped)
                if m:
                    version = m.group(1)

            if version:
                for name in current_names:
                    if name not in result:  # keep first resolved version
                        result[name] = version
                current_names = []

    return result


def parse_package_json(path: pathlib.Path) -> set[str]:
    """Return direct dependency names from package.json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    names: set[str] = set()
    for section in ("dependencies", "devDependencies"):
        block = (data or {}).get(section) or {}
        if isinstance(block, dict):
            names.update(block.keys())
    return names


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


# ---------- main ----------

def main() -> None:
    app_dirs = collect_app_dirs()
    if not app_dirs:
        print(f"No app directories found under {OUTPUT_DIR}")
        return

    direct_versions: dict[str, set[str]] = defaultdict(set)
    transitive_versions: dict[str, set[str]] = defaultdict(set)
    all_versions: dict[str, set[str]] = defaultdict(set)
    app_usage: dict[str, int] = defaultdict(int)

    npm_parsed = 0
    npm_v1 = 0
    yarn_parsed = 0
    yarn_no_json = 0
    no_lock = 0

    for app_dir in app_dirs:
        npm_lock = app_dir / "package-lock.json"
        yarn_lock = app_dir / "yarn.lock"
        pkg_json = app_dir / "package.json"

        if npm_lock.exists():
            direct, transitive, has_split = parse_npm_lock(npm_lock)
            if direct or transitive:
                npm_parsed += 1
            if not has_split:
                npm_v1 += 1
            for name, version in direct.items():
                direct_versions[name].add(version)
                all_versions[name].add(version)
                app_usage[name] += 1
            for name, version in transitive.items():
                transitive_versions[name].add(version)
                all_versions[name].add(version)

        elif yarn_lock.exists():
            all_pkgs = parse_yarn_lock(yarn_lock)
            if not all_pkgs:
                continue
            yarn_parsed += 1
            direct_names = parse_package_json(pkg_json) if pkg_json.exists() else set()
            if not direct_names:
                yarn_no_json += 1
            for name, version in all_pkgs.items():
                all_versions[name].add(version)
                if direct_names:
                    if name in direct_names:
                        direct_versions[name].add(version)
                        app_usage[name] += 1
                    else:
                        transitive_versions[name].add(version)

        else:
            no_lock += 1

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
        "# React Native TPL Analysis",
        f"# App directories              : {len(app_dirs)}",
        f"# npm lock files analyzed      : {npm_parsed}",
        *(
            [f"# (npm v1, no split)           : {npm_v1}"]
            if npm_v1 else []
        ),
        f"# yarn lock files analyzed     : {yarn_parsed}",
        *(
            [f"# (yarn, no package.json)      : {yarn_no_json}"]
            if yarn_no_json else []
        ),
        *(
            [f"# (no lock file found)         : {no_lock}"]
            if no_lock else []
        ),
        f"# Direct   packages            : {d_pkgs}  ({d_pairs} TPL:version pairs)",
        f"# Transitive packages          : {t_pkgs}  ({t_pairs} TPL:version pairs)",
        f"# All packages                 : {a_pkgs}  ({a_pairs} TPL:version pairs)",
        "",
    ]

    total_parsed = npm_parsed + yarn_parsed
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
        "Top 20 Most Used React Native Libraries (Direct Dependencies)",
        ROOT / "tpl_chart.pdf",
    )


if __name__ == "__main__":
    main()
