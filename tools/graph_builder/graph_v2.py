"""Version 2 serialization and deterministic tile extraction. Standard library only.

Partition AFTER national topology/restriction expansion. This keeps identical
edge endpoints across every overlapping tile, including backbone intersections
with minor roads, and preserves only-turn bans whose allowed exit is omitted.
"""
from collections import Counter, defaultdict
import heapq
import math
import struct
import zlib

from graph_builder import (MAGIC, NODE, EDGE, TURN, CAR, WALK, PENALTY,
                           ACCESS_PRIVATE, ONEWAY_FWD, ONEWAY_BACK, ROUNDABOUT,
                           CLASSES)

INF = 0xffffffff
PORTAL = 1


def subset(graph, edge_rows, tile_id, tile_kind, backbone_ids=()):
    rows = sorted(set(edge_rows))
    if not rows:
        raise ValueError('Empty tile: ' + tile_id)
    node_rows = sorted({n for i in rows for n in graph['edges'][i][:2]},
                       key=lambda n: graph['osmNodeIds'][n])
    ni = {old: new for new, old in enumerate(node_rows)}
    ei = {old: new for new, old in enumerate(rows)}
    name_rows = sorted({n for i in rows for n in graph['edges'][i][8:10] if n != INF})
    si = {old: new for new, old in enumerate(name_rows)}
    geometry, edges = [], []
    for row in rows:
        e = list(graph['edges'][row])
        points = graph['geometry'][e[2]:e[2]+e[3]]
        e[0], e[1], e[2] = ni[e[0]], ni[e[1]], len(geometry)
        e[8], e[9] = si.get(e[8], INF), si.get(e[9], INF)
        edges.append(tuple(e))
        geometry.extend(points)
    # Keep the national grid origin/scale. Rebuilding per-tile grids can be done
    # later without changing topology; grid bbox covers all stored geometry.
    grid = {key: [ei[e] for e in members if e in ei]
            for key, members in graph['grid'].items() if any(e in ei for e in members)}
    ids = [graph['osmNodeIds'][n] for n in node_rows]
    portals = set(backbone_ids)
    return dict(formatVersion=2, region=tile_id, tileId=tile_id, tileKind=tile_kind,
                sourceTimestamp=graph['sourceTimestamp'], buildTimestamp=graph['sourceTimestamp'],
                snapshot=graph['sourceTimestamp'], bbox=graph['bbox'],
                nodes=[graph['nodes'][n] for n in node_rows], osmNodeIds=ids,
                nodeFlags=[PORTAL if n in portals else 0 for n in ids],
                edges=edges, geometry=geometry, names=[graph['names'][n] for n in name_rows],
                restrictions=sorted((ei[a], ni[v], ei[b], typ)
                                    for a, v, b, typ in graph['restrictions'] if a in ei and b in ei),
                grid=grid, landmarks=[])


def encode(graph):
    out = bytearray(MAGIC)
    def put(fmt, *values): out.extend(struct.pack('<'+fmt, *values))
    def string(s):
        raw = s.encode('utf-8')
        if not raw or len(raw) > 65535: raise ValueError('Invalid string length')
        put('H', len(raw)); out.extend(raw)
    if graph['tileKind'] not in (0, 1): raise ValueError('Invalid tile kind')
    if graph['snapshot'] != graph['sourceTimestamp']: raise ValueError('Snapshot mismatch')
    put('H', 2); string(graph['region'])
    put('qq', graph['sourceTimestamp'], graph['buildTimestamp'])
    put('iiii', *graph['bbox'])
    put('IIIII', *(len(graph[k]) for k in ('nodes','edges','geometry','names','restrictions')))
    put('B', graph['tileKind']); string(graph['tileId']); put('q', graph['snapshot'])
    for p, osm_id, flags in zip(graph['nodes'], graph['osmNodeIds'], graph['nodeFlags'], strict=True):
        put('iiqB', *p, osm_id, flags)
    for e in graph['edges']: out.extend(EDGE.pack(*e))
    for p in graph['geometry']: out.extend(NODE.pack(*p))
    for name in graph['names']: string(name)
    for r in graph['restrictions']: out.extend(TURN.pack(*r))
    put('I', len(graph['grid']))
    for key, members in sorted(graph['grid'].items()):
        put('qI', key, len(members))
        for e in members: put('I', e)
    landmarks = graph.get('landmarks', [])
    if graph['tileKind'] == 1 and landmarks: raise ValueError('Governorate cannot contain ALT')
    put('H', len(landmarks))
    for landmark in landmarks:
        put('I', landmark['nodeRow'])
        for direction in ('fromLandmark', 'toLandmark'):
            values = landmark[direction]
            if len(values) != len(graph['nodes']): raise ValueError('ALT row length')
            for value in values: put('I', value)
    put('I', zlib.crc32(out))
    return bytes(out)


def adjacency(graph):
    forward = [[] for _ in graph['nodes']]
    reverse = [[] for _ in graph['nodes']]
    for e in graph['edges']:
        if not e[7] & CAR: continue
        penalty = 1.
        if e[7] & PENALTY:
            penalty = 3. if e[6] == 15 else 2. if e[6] >= 16 else 1.5
        # Relax turn and destination-only penalties. This is a LOWER bound.
        cost = e[4] * .36 / e[5] * penalty
        for a, b, allowed in ((e[0],e[1],not e[7]&ONEWAY_BACK),
                              (e[1],e[0],not e[7]&ONEWAY_FWD)):
            if allowed:
                forward[a].append((b,cost)); reverse[b].append((a,cost))
    return forward, reverse


def distances(adj, start):
    out = [math.inf] * len(adj); out[start] = 0.
    heap = [(0.,start)]
    while heap:
        d, n = heapq.heappop(heap)
        if d != out[n]: continue
        for nxt, cost in adj[n]:
            nd = d + cost
            if nd < out[nxt]:
                out[nxt] = nd; heapq.heappush(heap,(nd,nxt))
    return out


def alt_tables(graph, count=16):
    forward, reverse = adjacency(graph)
    weak = [a+b for a,b in zip(forward,reverse)]
    candidates = {i for i, a in enumerate(weak) if a}
    nearest = [math.inf] * len(weak)
    landmarks = []
    def seconds(values):
        return [INF if not math.isfinite(v) else min(INF-1, math.floor(v)) for v in values]
    while candidates and len(landmarks) < count:
        # Lowest OSM id breaks ties; first landmark is the smallest id.
        row = min(candidates, key=lambda i: (-nearest[i], graph['osmNodeIds'][i]))
        candidates.remove(row)
        landmarks.append(dict(nodeRow=row, fromLandmark=seconds(distances(forward,row)),
                              toLandmark=seconds(distances(reverse,row))))
        nearest = [min(a,b) for a,b in zip(nearest,distances(weak,row))]
    return landmarks


def alt_bound(graph, start, target):
    bound = 0
    for l in graph['landmarks']:
        f, t = l['fromLandmark'], l['toLandmark']
        # Both distances are floored individually. Subtract one second before
        # taking a difference, otherwise the heuristic can overestimate.
        if f[start] != INF and f[target] != INF: bound = max(bound,f[target]-f[start]-1)
        if t[start] != INF and t[target] != INF: bound = max(bound,t[start]-t[target]-1)
    return bound


def summary(graph):
    edges = graph['edges']; nodes = graph['nodes']
    parent = list(range(len(nodes)))
    def root(n):
        while n != parent[n]:
            parent[n] = parent[parent[n]]; n = parent[n]
        return n
    for e in edges:
        if e[7] & CAR: parent[root(e[0])] = root(e[1])
    groups = defaultdict(list)
    for i,e in enumerate(edges):
        if e[7]&CAR: groups[root(e[0])].append(i)
    ordered = sorted(groups.values(), key=lambda v:(-len(v),v[0]))
    car = sum(map(len, ordered)); largest = len(ordered[0]) if ordered else 0
    isolated = []
    for rows in ordered[1:]:
        if len(rows) <= 20: continue
        nn = {n for i in rows for n in edges[i][:2]}
        isolated.append(dict(edges=len(rows), approximateLat=sum(nodes[n][0] for n in nn)/len(nn)/1e7,
                             approximateLon=sum(nodes[n][1] for n in nn)/len(nn)/1e7))
    def klass(e): return CLASSES[e[6]] if e[6] < 23 else 'service_access'
    result = dict(tileId=graph['tileId'], nodes=len(nodes), edges=len(edges),
                  edgesByClass=dict(sorted(Counter(klass(e) for e in edges).items())),
                  walkEdges=sum(bool(e[7]&WALK) for e in edges),
                  onewayEdges=sum(bool(e[7]&(ONEWAY_FWD|ONEWAY_BACK)) for e in edges),
                  roundaboutEdges=sum(bool(e[7]&ROUNDABOUT) for e in edges),
                  walkEdgesWithCarGrant=sum(bool(e[7]&WALK and e[7]&CAR) for e in edges),
                  accessPrivateEdges=sum(bool(e[7]&ACCESS_PRIVATE) for e in edges),
                  explicitNoEdges=sum(bool(e[7]&1024) for e in edges),
                  prohibitedTurns=len(graph['restrictions']),
                  largestCarWeakComponentEdges=largest,
                  largestCarWeakComponentRatio=largest/car if car else 0,
                  isolatedCarComponentsOver20=isolated,
                  carComponentSizes=[len(v) for v in ordered],
                  landmarkCount=len(graph.get('landmarks',[])))
    result['longestCarEdges'] = [dict(osmWayId=e[10], lengthM=e[4]/10, highwayClass=klass(e),
                                     name=graph['names'][e[8]] if e[8] != INF else None)
                               for e in sorted((e for e in edges if e[7]&CAR),key=lambda e:(-e[4],e[10],e[0]))[:10]]
    if result['largestCarWeakComponentRatio'] < .9:
        result['connectivityExplanation'] = (
            f'{len(ordered)} disconnected CAR weak components after polygon selection; '
            f'largest contains {largest} of {car} CAR edges. Geometry coverage and OSM '
            'access flags are preserved without inventing connecting roads. '
            'See component sizes and isolated component coordinates for investigation.')
    return result
