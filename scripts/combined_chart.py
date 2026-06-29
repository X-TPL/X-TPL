#!/usr/bin/env python3
"""
Direct dependency adoption distribution across all five groups.

Each panel shows every direct dependency sorted by adoption rate (% of repos),
highest first. No library names â€” the goal is to show the distribution shape
(steep dropoff from popular to niche) rather than rank individual libraries.

Saves combined_chart.pdf in the scripts/ directory.
Run from anywhere: python scripts/combined_chart.py
"""

import json
import pathlib
import xml.etree.ElementTree as ET
from collections import defaultdict

try:
    import yaml
except ImportError:
    yaml = None

SCRIPTS = pathlib.Path(__file__).parent.resolve()


# ---------- helpers ----------

def _sorted_pcts(usage: dict[str, int], total: int) -> list[float]:
    """All adoption percentages, sorted highest-first."""
    return sorted([c / total * 100 for c in usage.values()], reverse=True)


# ---------- per-framework collectors ----------

def collect_flutter() -> tuple[list[float], int]:
    if yaml is None:
        print("pyyaml not installed â€” Flutter unavailable (pip install pyyaml)")
        return [], 0
    output = SCRIPTS / "flutter" / "output"
    usage: dict[str, int] = defaultdict(int)
    total = 0
    for app_dir in sorted(output.iterdir()) if output.is_dir() else []:
        if not app_dir.is_dir():
            continue
        lock = app_dir / "pubspec.lock"
        if not lock.exists():
            continue
        try:
            data = yaml.safe_load(lock.read_text(encoding="utf-8"))
        except Exception:
            continue
        packages = (data or {}).get("packages") or {}
        direct_found = False
        for name, info in packages.items():
            if not isinstance(info, dict):
                continue
            if info.get("source") == "sdk":
                continue
            if info.get("dependency", "").startswith("direct"):
                usage[name] += 1
                direct_found = True
        if direct_found:
            total += 1
    return _sorted_pcts(usage, total), total


def _collect_npm(output_dir: pathlib.Path) -> tuple[list[float], int]:
    usage: dict[str, int] = defaultdict(int)
    total = 0
    for app_dir in sorted(output_dir.iterdir()) if output_dir.is_dir() else []:
        if not app_dir.is_dir():
            continue
        lock = app_dir / "package-lock.json"
        if not lock.exists():
            continue
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (data or {}).get("lockfileVersion", 1) < 2:
            continue
        root = (data.get("packages") or {}).get("", {})
        direct_names: set[str] = set()
        for section in ("dependencies", "devDependencies"):
            block = root.get(section) or {}
            if isinstance(block, dict):
                direct_names.update(block.keys())
        if not direct_names:
            continue
        counted: set[str] = set()
        for pkg_path in (data.get("packages") or {}):
            if not pkg_path:
                continue
            name = pkg_path.split("node_modules/")[-1].rstrip("/")
            if name in direct_names and name not in counted:
                usage[name] += 1
                counted.add(name)
        total += 1
    return _sorted_pcts(usage, total), total


def collect_maui() -> tuple[list[float], int]:
    output = SCRIPTS / "maui" / "output"
    usage: dict[str, int] = defaultdict(int)
    total = 0
    for app_dir in sorted(output.iterdir()) if output.is_dir() else []:
        if not app_dir.is_dir():
            continue
        lock = app_dir / "packages.lock.json"
        if lock.exists():
            try:
                data = json.loads(lock.read_text(encoding="utf-8"))
            except Exception:
                continue
            direct_found = False
            for _fw, pkgs in (data.get("dependencies") or {}).items():
                if not isinstance(pkgs, dict):
                    continue
                for name, info in pkgs.items():
                    if isinstance(info, dict) and info.get("type") == "Direct":
                        usage[name] += 1
                        direct_found = True
            if direct_found:
                total += 1
        else:
            csproj = next(iter(app_dir.glob("*.csproj")), None)
            if not csproj:
                continue
            try:
                tree = ET.parse(csproj)
            except Exception:
                continue
            found = False
            for ref in tree.iter("PackageReference"):
                name = ref.get("Include") or ref.get("Update")
                if not name:
                    continue
                version = ref.get("Version") or ref.get("version")
                if version is None:
                    v_el = ref.find("Version")
                    version = v_el.text if v_el is not None else None
                if (version or "").strip():
                    usage[name] += 1
                    found = True
            if found:
                total += 1
    return _sorted_pcts(usage, total), total


# ---------- chart ----------

COLORS = {
    "Flutter":           "#1565C0",
    "React Native (TS)": "#1B5E20",
    "React Native (JS)": "#E65100",
    "Cordova":           "#B71C1C",
    "MAUI":              "#4A148C",
}


def draw_panel(ax, pcts: list[float], total: int, label: str) -> None:
    color = COLORS.get(label, "#333333")

    if not pcts:
        ax.text(0.5, 0.5, "No data available", ha="center", va="center",
                transform=ax.transAxes, fontsize=13, color="grey")
        ax.set_title(label, fontsize=14, fontweight="bold")
        ax.axis("off")
        return

    import matplotlib.ticker as ticker

    ax.bar(range(len(pcts)), pcts, color=color, edgecolor="none", width=1.0)

    ax.set_title(label, fontsize=14, fontweight="bold", pad=8)
    ax.set_ylabel("Adoption (%, log scale)", fontsize=12)
    ax.set_xlabel("Libraries (sorted by adoption)", fontsize=12)
    ax.set_xlim(-1, len(pcts))
    ax.set_yscale("log")
    ax.set_ylim(max(0.01, min(pcts) * 0.5), max(pcts) * 2)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:g}%"))
    ax.yaxis.set_minor_formatter(ticker.NullFormatter())
    ax.set_xticks([])
    ax.yaxis.grid(True, which="both", linestyle="--", alpha=0.45, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="y", labelsize=11)


def main() -> None:
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.rcParams["pdf.fonttype"] = 42
        matplotlib.rcParams["ps.fonttype"] = 42
    except ImportError:
        print("matplotlib not installed â€” pip install matplotlib")
        return

    datasets = [
        ("Flutter",           collect_flutter()),
        ("React Native (TS)", _collect_npm(SCRIPTS / "RN" / "output_ts")),
        ("React Native (JS)", _collect_npm(SCRIPTS / "RN" / "output_js")),
        ("Cordova",           _collect_npm(SCRIPTS / "cordova" / "output")),
        ("MAUI",              collect_maui()),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(20, 10))
    fig.suptitle(
        "Direct Dependency Adoption Distribution by Framework",
        fontsize=16, fontweight="bold", y=1.02,
    )

    for ax, (name, (pcts, total)) in zip(axes.flat, datasets):
        draw_panel(ax, pcts, total, name)

    axes.flat[5].set_visible(False)

    fig.tight_layout(h_pad=3.5, w_pad=2.5)
    out = SCRIPTS / "combined_chart.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()

