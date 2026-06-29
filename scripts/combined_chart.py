#!/usr/bin/env python3
"""
Generate a single combined PDF comparing the top N most used direct dependencies
across Flutter, React Native (TypeScript), React Native (JavaScript), Cordova,
and MAUI.

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
    yaml = None  # Flutter section will be skipped with a message

SCRIPTS = pathlib.Path(__file__).parent.resolve()
N = 20  # bars per panel


# ---------- per-framework data collectors ----------

def _top(usage: dict[str, int], total: int, n: int) -> tuple[list[str], list[float]]:
    top = sorted(usage.items(), key=lambda x: x[1], reverse=True)[:n]
    names = [name for name, _ in reversed(top)]
    pcts = [count / total * 100 if total else 0 for _, count in reversed(top)]
    return names, pcts


def collect_flutter(n: int) -> tuple[list[str], list[float], int]:
    if yaml is None:
        print("pyyaml not installed — Flutter data unavailable (pip install pyyaml)")
        return [], [], 0
    output = SCRIPTS / "flutter" / "output"
    usage: dict[str, int] = defaultdict(int)
    parsed = 0
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
            parsed += 1
    return *_top(usage, parsed, n), parsed


def _collect_npm(output_dir: pathlib.Path, n: int) -> tuple[list[str], list[float], int]:
    usage: dict[str, int] = defaultdict(int)
    parsed = 0
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
        parsed += 1
    return *_top(usage, parsed, n), parsed


def collect_rn_ts(n: int) -> tuple[list[str], list[float], int]:
    return _collect_npm(SCRIPTS / "RN" / "output_ts", n)


def collect_rn_js(n: int) -> tuple[list[str], list[float], int]:
    return _collect_npm(SCRIPTS / "RN" / "output_js", n)


def collect_cordova(n: int) -> tuple[list[str], list[float], int]:
    return _collect_npm(SCRIPTS / "cordova" / "output", n)


def collect_maui(n: int) -> tuple[list[str], list[float], int]:
    output = SCRIPTS / "maui" / "output"
    usage: dict[str, int] = defaultdict(int)
    parsed = 0
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
                parsed += 1
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
                parsed += 1
    return *_top(usage, parsed, n), parsed


# ---------- chart ----------

COLORS = {
    "Flutter":               "#1565C0",
    "React Native (TS)":     "#1B5E20",
    "React Native (JS)":     "#E65100",
    "Cordova":               "#B71C1C",
    "MAUI":                  "#4A148C",
}


def draw_panel(ax, names: list[str], pcts: list[float], total: int,
               framework: str) -> None:
    color = COLORS.get(framework, "#333333")
    if not names:
        ax.text(0.5, 0.5, "No data available", ha="center", va="center",
                transform=ax.transAxes, fontsize=10, color="grey")
        ax.set_title(framework, fontsize=12, fontweight="bold")
        ax.axis("off")
        return

    bars = ax.barh(names, pcts, color=color, edgecolor="white", height=0.72)
    for bar, pct in zip(bars, pcts):
        ax.text(
            bar.get_width() + 0.4,
            bar.get_y() + bar.get_height() / 2,
            f"{pct:.1f}%",
            va="center", ha="left", fontsize=7.5,
        )

    ax.set_title(f"{framework}  (n = {total:,})", fontsize=11, fontweight="bold", pad=8)
    ax.set_xlabel("% of repositories", fontsize=8)
    ax.set_xlim(0, min(100, max(pcts) * 1.18))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="y", labelsize=7.5)
    ax.tick_params(axis="x", labelsize=8)


def main() -> None:
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.rcParams["pdf.fonttype"] = 42   # embeds fonts as TrueType (required by most journals)
        matplotlib.rcParams["ps.fonttype"] = 42
    except ImportError:
        print("matplotlib not installed — pip install matplotlib")
        return

    datasets = [
        ("Flutter",           collect_flutter(N)),
        ("React Native (TS)", collect_rn_ts(N)),
        ("React Native (JS)", collect_rn_js(N)),
        ("Cordova",           collect_cordova(N)),
        ("MAUI",              collect_maui(N)),
    ]

    # 2 rows × 3 cols = 6 slots; 6th is hidden
    bar_height = 0.45
    fig_h = max(8, N * bar_height * 2 + 4)
    fig, axes = plt.subplots(2, 3, figsize=(24, fig_h))
    fig.suptitle(
        f"Top {N} Most Used Direct Dependencies by Framework",
        fontsize=14, fontweight="bold", y=1.01,
    )

    for ax, (name, (names, pcts, total)) in zip(axes.flat, datasets):
        draw_panel(ax, names, pcts, total, name)

    # hide the unused 6th cell
    axes.flat[5].set_visible(False)

    fig.tight_layout(h_pad=3.5, w_pad=2.5)
    out = SCRIPTS / "combined_chart.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
