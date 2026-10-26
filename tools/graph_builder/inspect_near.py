#!/usr/bin/env python3
"""Private, local-only road inspection. Never invoke this CLI in CI.

Usage: python inspect_near.py LAT LON RADIUS_METRES region.osmxg
Coordinates are supplied at runtime; never commit personal inspection outputs.
"""
import argparse
import json
import math
from pathlib import Path

from graph_builder import (CAR, WALK, PENALTY, ACCESS_PRIVATE, DESTINATION_ONLY,
                           ONEWAY_FWD, ONEWAY_BACK, ROUNDABOUT, TRACK, LINK,
                           ACCESS_NO, CLASSES, RADIUS)
from inspect_graph import inspect

FLAGS = {CAR: "CAR", WALK: "WALK", PENALTY: "PENALTY", ACCESS_PRIVATE: "ACCESS_PRIVATE",
         DESTINATION_ONLY: "DESTINATION_ONLY", ONEWAY_FWD: "ONEWAY_FWD",
         ONEWAY_BACK: "ONEWAY_BACK", ROUNDABOUT: "ROUNDABOUT", TRACK: "TRACK",
         LINK: "LINK", ACCESS_NO: "ACCESS_NO"}


def segment_distance(lat, lon, a, b):
    """Local tangent-plane distance to the whole segment (not just nodes)."""
    scale = math.pi/180*RADIUS
    cosine = math.cos(math.radians(lat))
    ax, ay = (a[1]/1e7-lon)*scale*cosine, (a[0]/1e7-lat)*scale
    bx, by = (b[1]/1e7-lon)*scale*cosine, (b[0]/1e7-lat)*scale
    dx, dy = bx-ax, by-ay
    norm = dx*dx+dy*dy
    t = max(0, min(1, -(ax*dx+ay*dy)/norm)) if norm else 0
    return math.hypot(ax+t*dx, ay+t*dy)


def near(graph, lat, lon, radius):
    if not all(math.isfinite(x) for x in (lat, lon, radius)) or not -90 <= lat <= 90 or not -180 <= lon <= 180 or radius < 0:
        raise ValueError("Invalid coordinate or radius")
    rows = []
    for i, e in enumerate(graph["edges"]):
        shape = graph["geometry"][e[2]:e[2]+e[3]]
        distance = min(segment_distance(lat, lon, a, b) for a, b in zip(shape, shape[1:]))
        if distance > radius:
            continue
        flags = e[7]
        def name(index):
            return None if index == 0xffffffff else graph["names"][index]
        rows.append({"edgeId": i, "osmWayId": e[10],
                     "highwayClass": CLASSES[e[6]] if e[6] < 23 else "service_access",
                     "flags": [value for mask, value in FLAGS.items() if flags & mask],
                     "direction": "forward" if flags & ONEWAY_FWD else "backward" if flags & ONEWAY_BACK else "both",
                     "carAllowed": bool(flags & CAR), "explicitOsmNo": bool(flags & ACCESS_NO),
                     "name": name(e[8]), "ref": name(e[9]), "distanceM": round(distance, 3),
                     "lengthM": e[4]/10, "speedKmh": e[5]})
    return sorted(rows, key=lambda r: (r["distanceM"], r["edgeId"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lat", type=float)
    parser.add_argument("lon", type=float)
    parser.add_argument("radius", type=float)
    parser.add_argument("graph", type=Path)
    parser.add_argument("--manifest", type=Path, help="Optional independently obtained SHA-256 manifest")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text()) if args.manifest else None
    graph = inspect(args.graph.read_bytes(), manifest)
    print(json.dumps({"regionId": graph["region"],
                      "distanceMethod": "local_tangent_plane_metres",
                      "tagNote": "Flags are serialized OSM classifications; not all raw OSM tags are stored.",
                      "edges": near(graph, args.lat, args.lon, args.radius)}, ensure_ascii=False, indent=2))
