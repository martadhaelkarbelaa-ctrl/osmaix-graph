#!/usr/bin/env python3
"""Run ONLY in GitHub Actions: verify PyPI releases, install, record versions."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request


def available(releases, version):
    return any(not f.get("yanked", False) for f in releases.get(version, []))


def select_osmium(releases):
    if available(releases, "4.3.0"):
        return "4.3.0"
    versions = [v for v in releases if re.fullmatch(r"4\.\d+\.\d+", v) and available(releases, v)]
    if not versions:
        raise ValueError("No non-yanked stable osmium 4.x release available")
    return max(versions, key=lambda v: tuple(map(int, v.split("."))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    subprocess.run([sys.executable, "-m", "pip", "index", "versions", "osmium"], check=True)
    def releases(package):
        with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/json", timeout=30) as response:
            return json.load(response)["releases"]
    selected = select_osmium(releases("osmium"))
    if not available(releases("pytest"), "8.4.2"):
        raise ValueError("Pinned pytest 8.4.2 is unavailable; do not silently change test framework")
    subprocess.run([sys.executable, "-m", "pip", "install", f"osmium=={selected}", "pytest==8.4.2"], check=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"osmium": selected, "pytest": "8.4.2",
        "osmiumFallbackUsed": selected != "4.3.0", "python": sys.version,
        "installed": subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True).splitlines()}, indent=2)+"\n")


if __name__ == "__main__":
    main()
