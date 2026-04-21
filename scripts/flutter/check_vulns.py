#!/usr/bin/env python3
"""
Check Flutter TPL versions against the OSV vulnerability database.

Reads every pubspec.lock under output/<app>/ (root level only), collects all
unique (package, version) pairs, queries https://api.osv.dev/v1/querybatch in
chunks of 500, and writes vuln_report.txt.

No external dependencies beyond PyYAML (already used by the project).
"""

import json
import pathlib
import time
import urllib.error
import urllib.request
from collections import defaultdict

import yaml

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "output"
REPORT_FILE = ROOT / "vuln_report.txt"

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
BATCH_SIZE = 500
ECOSYSTEM = "Pub"
_SKIP_SOURCES = {"sdk"}


# ---------- lock file parsing ----------

def collect_lock_files() -> list[pathlib.Path]:
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


def collect_pairs(lock_files: list[pathlib.Path]) -> list[tuple[str, str]]:
    """Return sorted list of unique (package, version) tuples."""
    seen: set[tuple[str, str]] = set()
    for lock in lock_files:
        for name, version in parse_lock(lock).items():
            seen.add((name, version))
    return sorted(seen)


# ---------- OSV querying ----------

def _post_json(url: str, payload: dict, retries: int = 3) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError(f"OSV query failed after {retries} retries")


def query_osv(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], list[dict]]:
    """Return {(package, version): [vuln, ...]} for every pair with findings."""
    results: dict[tuple[str, str], list[dict]] = {}

    for start in range(0, len(pairs), BATCH_SIZE):
        chunk = pairs[start: start + BATCH_SIZE]
        payload = {
            "queries": [
                {"version": ver, "package": {"name": pkg, "ecosystem": ECOSYSTEM}}
                for pkg, ver in chunk
            ]
        }
        response = _post_json(OSV_BATCH_URL, payload)
        for (pkg, ver), result in zip(chunk, response.get("results", [])):
            vulns = result.get("vulns") or []
            if vulns:
                results[(pkg, ver)] = vulns

        print(f"  queried {min(start + BATCH_SIZE, len(pairs))}/{len(pairs)} pairs ...", end="\r")

    print()
    return results


# ---------- severity helpers ----------

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}


def _severity(vuln: dict) -> str:
    """Extract the highest severity string from an OSV vuln entry."""
    for sev in vuln.get("severity") or []:
        score = sev.get("score", "")
        # CVSS v3 score → label
        try:
            s = float(score)
            if s >= 9.0:
                return "CRITICAL"
            if s >= 7.0:
                return "HIGH"
            if s >= 4.0:
                return "MEDIUM"
            return "LOW"
        except (ValueError, TypeError):
            pass
        # OSV sometimes puts the label directly
        label = str(sev.get("type", "")).upper()
        if label in _SEVERITY_ORDER:
            return label
    # fall back to database_specific CVSS if present
    for affected in vuln.get("affected") or []:
        for db_sev in (affected.get("database_specific") or {}).get("severity", []):
            if isinstance(db_sev, str) and db_sev.upper() in _SEVERITY_ORDER:
                return db_sev.upper()
    return "UNKNOWN"


# ---------- report ----------

def write_report(
    pairs: list[tuple[str, str]],
    findings: dict[tuple[str, str], list[dict]],
    lock_count: int,
) -> None:
    # group findings by package name (across all versions)
    by_package: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for (pkg, ver), vulns in findings.items():
        for v in vulns:
            by_package[pkg].append((ver, v))

    total_vulns = sum(len(v) for v in findings.values())

    lines = [
        "# Flutter TPL Vulnerability Report",
        f"# Lock files scanned  : {lock_count}",
        f"# Unique pairs queried: {len(pairs)}",
        f"# Vulnerable pairs    : {len(findings)}",
        f"# Vulnerable packages : {len(by_package)}",
        f"# Total vulnerabilities: {total_vulns}",
        "",
    ]

    if not by_package:
        lines.append("No vulnerabilities found.")
    else:
        # sort packages by worst severity across their vulns
        def worst(pkg: str) -> int:
            return min(
                _SEVERITY_ORDER.get(_severity(v), 4)
                for _, v in by_package[pkg]
            )

        for pkg in sorted(by_package, key=worst):
            entries = by_package[pkg]
            lines.append(f"{'=' * 60}")
            lines.append(f"PACKAGE: {pkg}")
            # sort by severity then version
            entries.sort(key=lambda x: (_SEVERITY_ORDER.get(_severity(x[1]), 4), x[0]))
            for ver, vuln in entries:
                sev = _severity(vuln)
                vid = vuln.get("id", "?")
                summary = vuln.get("summary") or vuln.get("details", "")[:120]
                lines.append(f"  [{sev}] {vid} @ {ver}")
                if summary:
                    lines.append(f"         {summary}")
            lines.append("")

    report = "\n".join(lines) + "\n"
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"Report written to {REPORT_FILE}")


# ---------- main ----------

def main() -> None:
    lock_files = collect_lock_files()
    if not lock_files:
        print(f"No pubspec.lock files found under {OUTPUT_DIR}")
        return

    print(f"Found {len(lock_files)} lock files — collecting packages ...")
    pairs = collect_pairs(lock_files)
    print(f"Querying OSV for {len(pairs)} unique (package, version) pairs ...")

    findings = query_osv(pairs)
    write_report(pairs, findings, len(lock_files))

    if findings:
        print(f"  {len(findings)} vulnerable (package, version) pairs across {len(set(p for p, _ in findings))} packages")
    else:
        print("  No vulnerabilities found.")


if __name__ == "__main__":
    main()
