#!/usr/bin/env python3
"""Build OSMXG1 deterministically. XML fixtures need only the standard library.

Production PBF ingestion uses pyosmium. No user overlays, GPS, credentials or
device data belong in this tool. See FORMAT.md for the cross-language contract.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zlib

CAR, WALK, PENALTY, ACCESS_PRIVATE, DESTINATION_ONLY = 1, 2, 4, 8, 16
ONEWAY_FWD, ONEWAY_BACK, ROUNDABOUT, TRACK, LINK = 32, 64, 128, 256, 512
# Distinguish an effective explicit OSM prohibition from learnable private/
# unknown access. Without this bit the phone could not enforce continue §1.
ACCESS_NO = 1024
MAGIC = b"OSMXG1\0\0"
EDGE = struct.Struct("<IIIHIBB HIIq".replace(" ", ""))
NODE = struct.Struct("<ii")
TURN = struct.Struct("<IIIB")
RADIUS = 6371008.8
CLASSES = (
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
    "unclassified", "residential", "living_street", "road", "service", "track",
    "footway", "path", "pedestrian", "steps", "cycleway", "bridleway", "corridor",
)
DEFAULT_SPEED = dict(zip(CLASSES, (90, 70, 50, 45, 40, 40, 40, 40, 40, 40,
                                  30, 25, 10, 25, 15, 15, 5, 5, 5, 5, 5, 5, 5)))
SUPPORTED_TURNS = {"no_left_turn", "no_right_turn", "no_straight_on", "no_u_turn",
                   "only_left_turn", "only_right_turn", "only_straight_on", "only_u_turn"}


@dataclass(frozen=True)
class Way:
    id: int
    nodes: tuple[int, ...]
    tags: dict[str, str]


@dataclass(frozen=True)
class Relation:
    id: int
    members: tuple[tuple[str, int, str], ...]
    tags: dict[str, str]


def distance(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = p2-p1, math.radians(b[1]-a[1])
    h = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2*RADIUS*math.asin(min(1, math.sqrt(max(0, h))))


def classify(tags):
    """Return (class, flags, integer speed); unsupported highways are omitted.

    Only an explicit vehicle-mode grant promotes a pedestrian facility to CAR.
    Generic access=yes does not mean motorcar=yes (accepted safety refinement).
    """
    highway = tags.get("highway")
    if highway not in DEFAULT_SPEED:
        return None
    flags = CAR if CLASSES.index(highway) < 16 else WALK
    if highway in ("service", "track"):
        flags |= PENALTY
    if highway == "track":
        flags |= TRACK
    if highway.endswith("_link"):
        flags |= LINK
    for key in ("motorcar", "motor_vehicle", "vehicle", "access"):
        if key not in tags:
            continue
        value = tags[key].strip().lower()
        if value in ("no", "private", "agricultural", "forestry"):
            flags = (flags & ~CAR) | ACCESS_PRIVATE
            if value == "no":
                flags |= ACCESS_NO
        elif value == "destination":
            flags |= DESTINATION_ONLY
        elif value in ("yes", "permissive", "designated"):
            if key != "access":
                flags |= CAR
        else:
            # Delivery/customer-only, unknown and conditional-only permissions
            # must not silently become unrestricted through routes.
            flags = (flags & ~CAR) | ACCESS_PRIVATE
        break
    oneway = tags.get("oneway", "").lower()
    roundabout = tags.get("junction") in ("roundabout", "circular")
    if oneway in ("yes", "true", "1"):
        flags |= ONEWAY_FWD
    elif oneway in ("-1", "reverse"):
        flags |= ONEWAY_BACK
    elif oneway not in ("no", "false", "0"):
        if oneway:
            flags &= ~CAR  # reversible/alternating is not a fixed car direction
        elif roundabout or highway in ("motorway", "motorway_link"):
            flags |= ONEWAY_FWD
    if roundabout:
        flags |= ROUNDABOUT
    speed = DEFAULT_SPEED[highway]
    if flags & CAR and flags & WALK:
        speed = 15
        flags |= PENALTY
    raw = tags.get("maxspeed", "")
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kph)?\s*", raw)
    if match:
        speed = min(120, max(1, float(match[1]) * (1.609344 if match[2] == "mph" else 1)))
    if roundabout:
        speed *= .7
    return CLASSES.index(highway), flags, max(1, min(120, int(speed + .5)))


def read_osm(path):
    path = Path(path)
    nodes, ways, relations = {}, [], []
    if path.suffix == ".pbf":
        try:
            import osmium
        except ImportError as exc:
            raise RuntimeError("PBF requires pyosmium; install requirements.txt") from exc
        class Handler(osmium.SimpleHandler):
            def way(self, w):
                tags = dict(w.tags)
                if classify(tags) is None:
                    return
                refs = []
                for n in w.nodes:
                    if not n.location.valid():
                        raise ValueError(f"Missing node {n.ref} in way {w.id}")
                    nodes[n.ref] = (n.lat, n.lon)
                    refs.append(n.ref)
                ways.append(Way(w.id, tuple(refs), tags))
            def relation(self, r):
                if r.tags.get("type") == "restriction":
                    relations.append(Relation(r.id, tuple((m.type, m.ref, m.role) for m in r.members), dict(r.tags)))
        Handler().apply_file(str(path), locations=True, idx="flex_mem")
    else:
        for _, obj in ET.iterparse(path, events=("end",)):
            if obj.tag == "node":
                nodes[int(obj.attrib["id"])] = (float(obj.attrib["lat"]), float(obj.attrib["lon"]))
            elif obj.tag == "way":
                tags = {t.attrib["k"]: t.attrib["v"] for t in obj.findall("tag")}
                if classify(tags) is not None:
                    ways.append(Way(int(obj.attrib["id"]), tuple(int(n.attrib["ref"]) for n in obj.findall("nd")), tags))
            elif obj.tag == "relation":
                tags = {t.attrib["k"]: t.attrib["v"] for t in obj.findall("tag")}
                if tags.get("type") == "restriction":
                    members = tuple((m.attrib["type"][0], int(m.attrib["ref"]), m.attrib["role"]) for m in obj.findall("member"))
                    relations.append(Relation(int(obj.attrib["id"]), members, tags))
            else:
                continue
            obj.clear()
    return nodes, ways, relations


def _cells(a, b):
    """Supercover at every grid boundary; include both sides of boundary lines."""
    ts = {0., 1.}
    for axis in (0, 1):
        lo, hi = sorted((a[axis], b[axis]))
        delta = b[axis]-a[axis]
        if delta:
            for line in range(math.floor(lo)+1, math.floor(hi)+1):
                t = (line-a[axis])/delta
                if 0 <= t <= 1:
                    ts.add(t)
    times = sorted(ts)
    times += [(x+y)/2 for x, y in zip(times, times[1:])]
    for t in times:
        x, y = (a[k]+(b[k]-a[k])*t for k in (0, 1))
        xs, ys = {math.floor(x)}, {math.floor(y)}
        if abs(x-round(x)) < 1e-8:
            xs.add(round(x)-1)
        if abs(y-round(y)) < 1e-8:
            ys.add(round(y)-1)
        for xx in xs:
            for yy in ys:
                key = ((xx & 0xffffffff) << 32) | (yy & 0xffffffff)
                yield key if key < 2**63 else key-2**64


def can_depart(edge, node):
    return bool(edge[7] & CAR) and (
        edge[0] == node and not edge[7] & ONEWAY_BACK or
        edge[1] == node and not edge[7] & ONEWAY_FWD)


def can_arrive(edge, node):
    return bool(edge[7] & CAR) and (
        edge[1] == node and not edge[7] & ONEWAY_BACK or
        edge[0] == node and not edge[7] & ONEWAY_FWD)


def build(nodes, ways, relations, region, bbox, source_ms, build_ms=None):
    if not re.fullmatch(r"[a-z0-9_-]{1,80}", region):
        raise ValueError("Invalid region identifier")
    if len(bbox) != 4 or not (-90 <= bbox[0] < bbox[2] <= 90 and -180 <= bbox[1] < bbox[3] <= 180):
        raise ValueError("bbox order is minLat,minLon,maxLat,maxLon")
    if source_ms < 0 or (build_ms is not None and build_ms < 0):
        raise ValueError("Timestamps must be nonnegative epoch milliseconds")
    # Use exactly the coordinates the phone will read for geometry and grid.
    bbox = [round(v*1e7)/1e7 for v in bbox]
    nodes = {n: tuple(round(v*1e7)/1e7 for v in point) for n, point in nodes.items()}
    ways = sorted((w for w in ways if classify(w.tags) is not None), key=lambda w: w.id)
    if len({w.id for w in ways}) != len(ways):
        raise ValueError("Duplicate way ID")
    if not ways:
        raise ValueError("No supported highway ways")
    usage = Counter(n for w in ways for n in set(w.nodes))
    cuts = {n for n, count in usage.items() if count > 1}
    for r in relations:
        cuts.update(ref for kind, ref, role in r.members if role == "via" and kind == "n")
    for w in ways:
        if len(w.nodes) < 2:
            raise ValueError(f"Way {w.id} has fewer than two nodes")
        cuts.update((w.nodes[0], w.nodes[-1]))
        cuts.update(n for n, count in Counter(w.nodes).items() if count > 1)
        cuts.update(w.nodes[65534::65534])
        for n in w.nodes:
            if n not in nodes:
                raise ValueError(f"Missing node {n} in way {w.id}")
            lat, lon = nodes[n]
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f"Invalid coordinate at node {n}")
    used_cuts = sorted(cuts & set(usage))
    ids = {n: i for i, n in enumerate(used_cuts)}
    names = sorted({s for w in ways for s in (w.tags.get("name:ar") or w.tags.get("name"), w.tags.get("ref")) if s})
    name_ids = {s: i for i, s in enumerate(names)}
    geometry, edges, way_edges = [], [], defaultdict(list)
    # service subtypes are represented by separate class IDs; otherwise the
    # binary format cannot distinguish the specified 1.5x and 2x costs.
    for w in ways:
        klass, flags, speed = classify(w.tags)
        if w.tags.get("highway") == "service" and w.tags.get("service") in ("parking_aisle", "driveway"):
            klass = 23
        start = 0
        for i in range(1, len(w.nodes)):
            if w.nodes[i] not in cuts:
                continue
            shape = [nodes[n] for n in w.nodes[start:i+1]]
            length = sum(distance(a, b) for a, b in zip(shape, shape[1:]))
            if length > 0:
                edge = (ids[w.nodes[start]], ids[w.nodes[i]], len(geometry), len(shape),
                        max(1, int(length*10+.5)), speed, klass, flags,
                        name_ids.get(w.tags.get("name:ar") or w.tags.get("name"), 0xffffffff),
                        name_ids.get(w.tags.get("ref"), 0xffffffff), w.id)
                way_edges[w.id].append(len(edges))
                edges.append(edge)
                geometry.extend(shape)
            start = i
    if not edges:
        raise ValueError("No nonzero edges")
    incident = defaultdict(list)
    for i, e in enumerate(edges):
        incident[e[0]].append(i)
        if e[1] != e[0]:
            incident[e[1]].append(i)
    restrictions, reasons, applied_relations = set(), Counter(), 0
    for r in sorted(relations, key=lambda r: r.id):
        by_role = {role: [(kind, ref) for kind, ref, rr in r.members if rr == role] for role in ("from", "via", "to")}
        if any(kind == "w" for kind, _ in by_role["via"]):
            reasons["via_way"] += 1
            continue
        if any(len(by_role[x]) != 1 for x in by_role):
            reasons["unsupported_members"] += 1
            continue
        if any(k in r.tags for k in ("restriction:conditional", "restriction:motorcar:conditional", "restriction:motor_vehicle:conditional")):
            reasons["conditional"] += 1
            continue
        if set(r.tags.get("except", "").replace(" ", "").split(";")) & {"motorcar", "motor_vehicle", "vehicle"}:
            reasons["car_exempt"] += 1
            continue
        typ = r.tags.get("restriction:motorcar", r.tags.get("restriction:motor_vehicle", r.tags.get("restriction", "")))
        if typ not in SUPPORTED_TURNS:
            reasons["unsupported_type"] += 1
            continue
        (fk, fw), (vk, vn), (tk, tw) = (by_role[x][0] for x in ("from", "via", "to"))
        if (fk, vk, tk) != ("w", "n", "w") or vn not in ids:
            reasons["unresolved"] += 1
            continue
        via = ids[vn]
        incoming = [e for e in way_edges[fw] if can_arrive(edges[e], via)]
        permitted = {e for e in way_edges[tw] if can_depart(edges[e], via)}
        if not incoming or not permitted:
            reasons["unresolved"] += 1
            continue
        for first in incoming:
            targets = {first} & permitted if typ.endswith("u_turn") and fw == tw else permitted
            targets = ({e for e in incident[via] if can_depart(edges[e], via)}-targets
                       if typ.startswith("only_") else targets)
            restrictions.update((first, via, last, 0) for last in targets)
        applied_relations += 1
    grid = defaultdict(set)
    scale = math.pi/180*RADIUS/250
    cosine = math.cos(math.radians((bbox[0]+bbox[2])/2))
    def project(p):
        return ((p[1]-bbox[1])*scale*cosine, (p[0]-bbox[0])*scale)
    for i, e in enumerate(edges):
        points = geometry[e[2]:e[2]+e[3]]
        for a, b in zip(points, points[1:]):
            for cell in _cells(project(a), project(b)):
                grid[cell].add(i)
    out = bytearray(MAGIC)
    def put(fmt, *args):
        out.extend(struct.pack("<"+fmt, *args))
    def string(value):
        raw = value.encode("utf-8")
        if len(raw) > 65535:
            raise ValueError("String exceeds u16 UTF-8 length")
        put("H", len(raw)); out.extend(raw)
    put("H", 1); string(region)
    # Default build timestamp is a logical reproducible build epoch, not now().
    put("qq", source_ms, source_ms if build_ms is None else build_ms)
    put("iiii", *(round(x*1e7) for x in bbox))
    put("IIIII", len(ids), len(edges), len(geometry), len(names), len(restrictions))
    for n in used_cuts:
        out.extend(NODE.pack(*(round(x*1e7) for x in nodes[n])))
    for e in edges:
        out.extend(EDGE.pack(*e))
    for p in geometry:
        out.extend(NODE.pack(*(round(x*1e7) for x in p)))
    for name in names:
        string(name)
    for r in sorted(restrictions):
        out.extend(TURN.pack(*r))
    put("I", len(grid))
    for key, members in sorted(grid.items()):
        put("qI", key, len(members))
        for i in sorted(members):
            put("I", i)
    put("I", zlib.crc32(out))
    # Weak CAR components: explicitly named, not confused with reachability
    # under one-way and turn restrictions (the local router must test that).
    parent = list(range(len(ids)))
    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]; n = parent[n]
        return n
    for e in edges:
        if e[7] & CAR:
            parent[root(e[0])] = root(e[1])
    components = Counter(root(e[0]) for e in edges if e[7] & CAR)
    largest = max(components.values(), default=0)
    car_count = sum(components.values())
    report = {
        "regionId": region, "sourceTimestamp": source_ms, "bytes": len(out),
        "nodes": len(ids), "edges": len(edges), "geometryPoints": len(geometry),
        "edgesByClass": dict(sorted(Counter((CLASSES[e[6]] if e[6] < 23 else "service_access") for e in edges).items())),
        "accessPrivateEdges": sum(bool(e[7] & ACCESS_PRIVATE) for e in edges),
        "explicitNoEdges": sum(bool(e[7] & ACCESS_NO) for e in edges),
        "walkEdges": sum(bool(e[7] & WALK) for e in edges),
        "onewayEdges": sum(bool(e[7] & (ONEWAY_FWD | ONEWAY_BACK)) for e in edges),
        "roundaboutEdges": sum(bool(e[7] & ROUNDABOUT) for e in edges),
        "namedCarEdgesRatio": sum(bool(e[7] & CAR) and e[8] != 0xffffffff for e in edges)/car_count if car_count else 0,
        "walkEdgesWithCarGrant": sum(bool(e[7] & WALK) and bool(e[7] & CAR) for e in edges),
        "longestCarEdges": [{"edgeId": i, "osmWayId": e[10], "lengthM": e[4]/10,
                             "highwayClass": CLASSES[e[6]] if e[6] < 23 else "service_access",
                             "name": names[e[8]] if e[8] != 0xffffffff else None}
                            for i, e in sorted(((i, e) for i, e in enumerate(edges) if e[7] & CAR),
                                               key=lambda pair: (-pair[1][4], pair[0]))[:10]],
        "appliedRestrictionRelations": applied_relations, "prohibitedTurns": len(restrictions),
        "ignoredRestrictionRelations": dict(sorted(reasons.items())),
        "largestCarWeakComponentEdges": largest,
        "largestCarWeakComponentRatio": largest/car_count if car_count else 0,
        "otherCarWeakComponentsOver20": sorted((n for n in components.values() if n > 20), reverse=True),
        "gridCells": len(grid), "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
        "limitations": ["via-way and conditional restrictions are reported, not applied",
                        "No buildings, live closures, or personal permissions are included"],
    }
    if largest > 20:
        report["otherCarWeakComponentsOver20"].remove(largest)
    manifest = {"regionId": region, "file": f"{region}.osmxg", "bytes": len(out),
                "sha256": hashlib.sha256(out).hexdigest(), "sourceTimestamp": source_ms,
                "formatVersion": 1, "bbox": bbox}
    return bytes(out), manifest, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--region", required=True)
    parser.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("MIN_LAT", "MIN_LON", "MAX_LAT", "MAX_LON"))
    parser.add_argument("--source-timestamp", required=True, help="UTC ISO 8601 or integer milliseconds")
    parser.add_argument("--build-timestamp", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = args.source_timestamp
    if value.isdigit():
        timestamp = int(value)
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            parser.error("Source timestamp must include timezone")
        timestamp = int(dt.timestamp()*1000)
    data, manifest, report = build(*read_osm(args.input), args.region, args.bbox, timestamp, args.build_timestamp)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / manifest["file"]).write_bytes(data)
    for name, obj in (("manifest", manifest), ("report", report)):
        (args.output / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"file": manifest["file"], "bytes": len(data), "edges": report["edges"], "sha256": manifest["sha256"]}))


if __name__ == "__main__":
    main()
