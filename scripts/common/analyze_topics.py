#!/usr/bin/env python3
"""
Analyze GitHub topics across all framework repos.json files.

Searches for repos.json in every sibling directory of this script's parent
(i.e. scripts/RN, scripts/flutter, scripts/maui, scripts/unity, scripts/cordova …),
counts topic frequencies per framework and across all frameworks, and writes
topic_analysis.txt next to this script.

Usage:
    python analyze_topics.py [--top N]   # default: top 30 per section
"""

import argparse
import json
import pathlib
from collections import Counter

COMMON_DIR = pathlib.Path(__file__).parent.resolve()
SCRIPTS_DIR = COMMON_DIR.parent
OUTPUT_FILE = COMMON_DIR / "topic_analysis.txt"

# Directories to skip when looking for repos.json
_SKIP_DIRS = {"common", "assets", ".idea", "__pycache__"}


# ---------- discovery ----------

def find_repos_files() -> dict[str, pathlib.Path]:
    """Return {framework_name: path_to_repos.json} for every framework that has one."""
    found = {}
    for d in sorted(SCRIPTS_DIR.iterdir()):
        if not d.is_dir() or d.name in _SKIP_DIRS:
            continue
        candidate = d / "repos.json"
        if candidate.exists():
            found[d.name] = candidate
    return found


# ---------- parsing ----------

def load_topics(repos_file: pathlib.Path) -> tuple[Counter, int, int]:
    """
    Return (topic_counter, total_repos, buildable_repos) from a repos.json.
    Repos with an empty topics list are still counted in totals.
    """
    with repos_file.open(encoding="utf-8") as f:
        repos = json.load(f)

    counter: Counter = Counter()
    buildable = 0

    for repo in repos:
        for topic in repo.get("topics") or []:
            counter[topic] += 1
        if repo.get("buildable"):
            buildable += 1

    return counter, len(repos), buildable


# ---------- formatting ----------

def _bar(count: int, max_count: int, width: int = 30) -> str:
    filled = round(width * count / max_count) if max_count else 0
    return "#" * filled + "-" * (width - filled)


def _section(
    title: str,
    counter: Counter,
    total_repos: int,
    buildable_repos: int,
    top_n: int,
) -> list[str]:
    lines = [
        f"{'=' * 60}",
        f"  {title}",
        f"{'=' * 60}",
        f"  Total repos    : {total_repos}",
        f"  Buildable repos: {buildable_repos}",
        f"  Unique topics  : {len(counter)}",
        f"  Top {top_n} topics (by repo count):",
        "",
    ]

    top = counter.most_common(top_n)
    max_count = top[0][1] if top else 1
    max_label = max((len(t) for t, _ in top), default=1)

    for topic, count in top:
        pct = 100.0 * count / total_repos if total_repos else 0.0
        bar = _bar(count, max_count)
        lines.append(
            f"  {topic:<{max_label}}  {bar}  {count:>5}  ({pct:5.1f}%)"
        )

    lines.append("")
    return lines


# ---------- main ----------

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze GitHub topics across repos.json files")
    parser.add_argument("--top", type=int, default=30, metavar="N",
                        help="number of top topics to show per framework (default: 30)")
    args = parser.parse_args()
    top_n = args.top

    repos_files = find_repos_files()
    if not repos_files:
        print(f"No repos.json files found under {SCRIPTS_DIR}")
        return

    print(f"Found repos.json in: {', '.join(repos_files)}")

    all_topics: Counter = Counter()
    all_total = 0
    all_buildable = 0

    framework_data: dict[str, tuple[Counter, int, int]] = {}
    for framework, path in repos_files.items():
        counter, total, buildable = load_topics(path)
        framework_data[framework] = (counter, total, buildable)
        all_topics.update(counter)
        all_total += total
        all_buildable += buildable
        print(f"  [{framework}] {total} repos, {buildable} buildable, {len(counter)} unique topics")

    lines = [
        "# GitHub Topic Analysis",
        f"# Frameworks analyzed : {len(repos_files)}  ({', '.join(repos_files)})",
        f"# Total repos         : {all_total}",
        f"# Total buildable     : {all_buildable}",
        f"# Total unique topics : {len(all_topics)}",
        "",
    ]

    # ---- per-framework sections ----
    for framework, (counter, total, buildable) in framework_data.items():
        lines.extend(_section(
            title=framework.upper(),
            counter=counter,
            total_repos=total,
            buildable_repos=buildable,
            top_n=top_n,
        ))

    # ---- combined section ----
    lines.extend(_section(
        title="ALL FRAMEWORKS (COMBINED)",
        counter=all_topics,
        total_repos=all_total,
        buildable_repos=all_buildable,
        top_n=top_n,
    ))

    report = "\n".join(lines) + "\n"
    OUTPUT_FILE.write_text(report, encoding="utf-8")
    print(f"\nReport written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
