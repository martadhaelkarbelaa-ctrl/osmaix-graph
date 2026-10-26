"""Independent structural validator for OSMXG1; rejects partial/corrupt data."""
import hashlib
import math
import struct
import zlib


def inspect(data, manifest=None):
    if manifest is not None:
        if manifest.get("formatVersion", 2) not in (1, 2) or manifest.get("bytes") != len(data):
            raise ValueError("Manifest format/size mismatch")
        if manifest.get("sha256") != hashlib.sha256(data).hexdigest():
            raise ValueError("Manifest SHA-256 mismatch")
    if len(data) < 64 or data[:8] != b"OSMXG1\0\0":
        raise ValueError("Not an OSMXG1 graph")
    if zlib.crc32(data[:-4]) != struct.unpack_from("<I", data, len(data)-4)[0]:
        raise ValueError("CRC mismatch")
    offset, end = 8, len(data)-4
    def take(fmt):
        nonlocal offset
        size = struct.calcsize("<"+fmt)
        if offset+size > end:
            raise ValueError("Truncated graph")
        result = struct.unpack_from("<"+fmt, data, offset)
        offset += size
        return result
    def text():
        nonlocal offset
        size, = take("H")
        if offset+size > end:
            raise ValueError("Truncated string")
        result = data[offset:offset+size].decode("utf-8", errors="strict")
        offset += size
        return result
    version, = take("H")
    if version not in (1, 2):
        raise ValueError("Unknown graph version")
    if manifest is not None and manifest.get('formatVersion', 2) != version:
        raise ValueError('Manifest/header version mismatch')
    region = text()
    source_ms, build_ms = take("qq")
    bbox = take("iiii")
    if not (-900000000 <= bbox[0] < bbox[2] <= 900000000 and
            -1800000000 <= bbox[1] < bbox[3] <= 1800000000):
        raise ValueError("Invalid bbox")
    nn, ne, ng, ns, nr = take("IIIII")
    tile_kind, tile_id, snapshot = None, None, None
    if version == 2:
        tile_kind, = take('B'); tile_id = text(); snapshot, = take('q')
        if tile_kind not in (0, 1) or tile_id != region or snapshot != source_ms or snapshot < 0:
            raise ValueError('Invalid tile metadata')
    if not nn or not ne or nn*(17 if version == 2 else 8)+ne*38+ng*8+ns*2+nr*13 > end-offset:
        raise ValueError("Impossible section counts")
    def coordinate():
        lat, lon = take("ii")
        if not -900000000 <= lat <= 900000000 or not -1800000000 <= lon <= 1800000000:
            raise ValueError("Invalid coordinate")
        return lat, lon
    nodes, osm_ids, node_flags = [], [], []
    for _ in range(nn):
        nodes.append(coordinate())
        if version == 2:
            osm_id, flags = take('qB')
            if osm_id <= 0 or flags & ~1 or (osm_ids and osm_id <= osm_ids[-1]):
                raise ValueError('Invalid OSM node identity/flags/order')
            osm_ids.append(osm_id); node_flags.append(flags)
    edges = [take("IIIHIBBHIIq") for _ in range(ne)]
    geometry = [coordinate() for _ in range(ng)]
    names = [text() for _ in range(ns)]
    restrictions = [take("IIIB") for _ in range(nr)]
    for edge in edges:
        a, b, start, count, length, speed, klass, flags, name, ref, _ = edge
        if a >= nn or b >= nn or count < 2 or start+count > ng:
            raise ValueError("Invalid edge topology")
        if geometry[start] != nodes[a] or geometry[start+count-1] != nodes[b]:
            raise ValueError("Geometry endpoint mismatch")
        if not length or not 1 <= speed <= 120 or klass > 23 or flags & ~2047 or flags & 96 == 96:
            raise ValueError("Invalid edge attributes")
        if flags & 1024 and (flags & 1 or not flags & 8):
            raise ValueError("Explicit no conflicts with car permission")
        if any(i != 0xffffffff and i >= ns for i in (name, ref)):
            raise ValueError("Invalid string reference")
    for a, via, b, typ in restrictions:
        if a >= ne or b >= ne or via >= nn or typ != 0 or via not in edges[a][:2] or via not in edges[b][:2]:
            raise ValueError("Invalid turn restriction")
    count, = take("I")
    if count*12 > end-offset:
        raise ValueError("Impossible grid count")
    grid = {}
    previous_key = -(2**63)-1
    for _ in range(count):
        key, size = take("qI")
        if key <= previous_key or size > ne:
            raise ValueError("Invalid grid ordering/count")
        members = [take("I")[0] for _ in range(size)]
        if members != sorted(set(members)) or any(i >= ne for i in members):
            raise ValueError("Invalid grid edge reference")
        previous_key = key
        grid[key] = members
    landmarks = []
    if version == 2:
        count, = take('H')
        if count > min(16, nn) or (tile_kind == 1 and count) or count*(4+nn*8) > end-offset:
            raise ValueError('Invalid ALT count')
        seen = set()
        for _ in range(count):
            row, = take('I')
            if row >= nn or row in seen: raise ValueError('Invalid ALT landmark')
            seen.add(row)
            forward = list(take('I'*nn)); reverse = list(take('I'*nn))
            if forward[row] != 0 or reverse[row] != 0: raise ValueError('Invalid ALT self distance')
            landmarks.append(dict(nodeRow=row, fromLandmark=forward, toLandmark=reverse))
    if offset != end:
        raise ValueError("Trailing graph data")
    if manifest is not None and version == 1 and (manifest.get("regionId") != region or manifest.get("sourceTimestamp") != source_ms or
                                [round(x*1e7) for x in manifest.get("bbox", [])] != list(bbox)):
        raise ValueError("Manifest metadata mismatch")
    if manifest is not None and version == 2:
        for key, actual in [('tileId',tile_id),('snapshot',snapshot),('formatVersion',version)]:
            if key in manifest and manifest[key] != actual: raise ValueError('Manifest tile metadata mismatch')
    return dict(formatVersion=version, region=region, sourceTimestamp=source_ms, buildTimestamp=build_ms,
                bbox=bbox, nodes=nodes, edges=edges, geometry=geometry, names=names,
                restrictions=restrictions, grid=grid, osmNodeIds=osm_ids, nodeFlags=node_flags,
                tileId=tile_id, tileKind=tile_kind, snapshot=snapshot, landmarks=landmarks)
