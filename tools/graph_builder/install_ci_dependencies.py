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


def select_version(releases, preferred):
    if available(releases, preferred): return preferred
    major = preferred.split('.')[0]
    versions = [v for v in releases if re.fullmatch(re.escape(major)+r"\.\d+\.\d+", v) and available(releases, v)]
    if not versions:
        raise ValueError("No non-yanked stable release in requested major version")
    return max(versions, key=lambda v: tuple(map(int, v.split("."))))


def select_osmium(releases):
    return select_version(releases, "4.3.0")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for package in ("osmium", "pytest"):
        subprocess.run([sys.executable, "-m", "pip", "index", "versions", package], check=True)
    def releases(package):
        with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/json", timeout=30) as response:
            return json.load(response)["releases"]
    chosen = {name: select_version(releases(name), version) for name, version in
              (("osmium","4.3.0"),("pytest","8.4.2"),("shapely","2.1.2"),("pyproj","3.7.2"))}
    subprocess.run([sys.executable, "-m", "pip", "install", *[f"{k}=={v}" for k,v in chosen.items()]], check=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"selected": chosen,
        "osmiumFallbackUsed": chosen["osmium"] != "4.3.0",
        "pytestFallbackUsed": chosen["pytest"] != "8.4.2", "python": sys.version,
        "installed": subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True).splitlines()}, indent=2)+"\n")



if __name__ == "__main__":
    main()
