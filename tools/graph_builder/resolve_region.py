#!/usr/bin/env python3
"""Derive governorate bbox + margin and source epoch from the input PBF."""
import argparse
import json
import math
import sys
from pathlib import Path


def is_karbala_candidate(tags):
    names = " ".join(tags.get(key, "") for key in ("name", "name:ar", "name:en", "official_name", "alt_name"))
    return (tags.get("boundary") == "administrative" and tags.get("admin_level") == "4"
            and ("كربلاء" in names or "karbala" in names.casefold()))


def resolve(path, config):
    import osmium
    matches = []
    candidates = []
    class Relations(osmium.SimpleHandler):
        def relation(self, r):
            if is_karbala_candidate(r.tags):
                candidates.append({"osmRelationId": r.id, "tags": dict(r.tags)})
            if (r.tags.get(config["boundary_tag"]) == config["boundary_value"] and
                    r.tags.get("boundary") == "administrative" and
                    r.tags.get("admin_level") == config["admin_level"]):
                matches.append((r.id, [(m.type, m.ref, m.role) for m in r.members]))
    Relations().apply_file(str(path))
    if len(matches) != 1:
        print(json.dumps({"karbalaAdmin4Candidates": sorted(candidates, key=lambda row: row["osmRelationId"])},
                         ensure_ascii=False, sort_keys=True), file=sys.stderr)
        raise ValueError(f"Expected one governorate boundary, found {len(matches)}")
    boundary_id, members = matches[0]
    if any(t == "r" and role in ("outer", "inner", "") for t, _, role in members):
        raise ValueError("Nested boundary relation needs explicit support, not a guessed bbox")
    wanted = {ref for typ, ref, role in members if typ == "w" and role in ("outer", "")}
    if not wanted:
        raise ValueError("Boundary has no outer ways")
    found = set()
    extent = [90., 180., -90., -180.]
    class Boundaries(osmium.SimpleHandler):
        def way(self, w):
            if w.id not in wanted:
                return
            found.add(w.id)
            for n in w.nodes:
                if not n.location.valid():
                    raise ValueError("Missing boundary node")
                extent[0] = min(extent[0], n.lat); extent[1] = min(extent[1], n.lon)
                extent[2] = max(extent[2], n.lat); extent[3] = max(extent[3], n.lon)
    Boundaries().apply_file(str(path), locations=True, idx="flex_mem")
    if found != wanted:
        raise ValueError("Incomplete governorate boundary")
    latitude_margin = config["margin_m"]/111195.0802335329
    longitude_margin = latitude_margin / math.cos(math.radians(max(abs(extent[0]), abs(extent[2]))))
    bbox = [extent[0]-latitude_margin, extent[1]-longitude_margin,
            extent[2]+latitude_margin, extent[3]+longitude_margin]
    with osmium.io.Reader(str(path)) as reader:
        source = reader.header().get("osmosis_replication_timestamp")
    if not source:
        raise ValueError("PBF has no replication timestamp; do not substitute today's date")
    return {"bbox": bbox, "sourceTimestamp": source, "osmBoundaryRelation": boundary_id,
            "margin_m": config["margin_m"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--region", default="karbala")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("regions.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(resolve(args.input, json.loads(args.config.read_text())[args.region]), indent=2)+"\n")
