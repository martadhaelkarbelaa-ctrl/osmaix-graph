"""Strict PBF administrative boundaries; no bbox or repaired-ring substitutes.

Geographic operations require shapely 2.x and pyproj 3.x in Actions. Raw
coordinates are GeoJSON lon/lat. Metric buffer/simplification use one local
azimuthal equidistant CRS per governorate. Input relations/areas must be valid.
"""
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


def tile_id(relation_id, tags):
    value = tags.get('ISO3166-2')
    if not value: return f'osm-r{relation_id}'
    if not re.fullmatch(r'IQ-[A-Z0-9]+', value):
        raise ValueError(f'Invalid Iraq ISO code on relation {relation_id}: {value}')
    return value.lower()


def metadata_error(tags, members):
    if any(kind == 'r' and role in ('outer','inner','') for kind,_,role in members):
        return 'Nested geometric boundary relation is unsupported'
    if not any(kind == 'w' and role in ('outer','') for kind,_,role in members):
        return 'Boundary has no outer ways'
    return None


def timestamp_ms(value):
    if not value: raise ValueError('Missing osmosis_replication_timestamp; no clock fallback')
    dt = datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None: raise ValueError('Snapshot timestamp requires timezone')
    return int(dt.timestamp()*1000)


def extract(path):
    import osmium
    from shapely.geometry import shape, mapping
    countries, candidates, errors = {}, {}, []
    class Metadata(osmium.SimpleHandler):
        def relation(self, r):
            t = dict(r.tags)
            members = [(m.type,m.ref,m.role) for m in r.members]
            if t.get('boundary') != 'administrative': return
            if t.get('admin_level') == '2' and t.get('ISO3166-1:alpha2',t.get('ISO3166-1')) == 'IQ':
                countries[r.id] = (t,members)
            if t.get('admin_level') == '4': candidates[r.id] = (t,members)
    Metadata().apply_file(str(path))
    if len(countries) != 1: raise ValueError(f'Expected one Iraq country relation, got {len(countries)}')
    country_id = next(iter(countries))
    wanted = {country_id, *candidates}
    definitions = {**countries, **candidates}
    wanted_ways = {ref for _,members in definitions.values()
                   for kind,ref,role in members if kind == 'w' and role in ('outer','inner','')}
    way_ends = {}
    bad_ways = set()
    areas = {}
    factory = osmium.geom.GeoJSONFactory()
    class Areas(osmium.SimpleHandler):
        def way(self, way):
            if way.id not in wanted_ways: return
            if len(way.nodes) < 2 or any(not n.location.valid() for n in way.nodes):
                bad_ways.add(way.id)
            else:
                way_ends[way.id] = (way.nodes[0].ref, way.nodes[-1].ref)
        def area(self, area):
            if area.from_way() or area.orig_id() not in wanted: return
            rid = area.orig_id()
            try:
                poly = shape(json.loads(factory.create_multipolygon(area)))
                if poly.is_empty or not poly.is_valid: raise ValueError('Invalid multipolygon')
                areas[rid] = poly
            except (ValueError, RuntimeError) as exc:
                errors.append({'relationId':rid,'error':str(exc)})
    Areas().apply_file(str(path),locations=True,idx='flex_mem')
    def completeness(rid):
        tags,members = definitions[rid]
        problem = metadata_error(tags,members)
        if problem: return problem
        refs = [ref for kind,ref,role in members if kind=='w' and role in ('outer','inner','')]
        missing = set(refs)-way_ends.keys()
        if missing or set(refs)&bad_ways: return 'Missing/invalid boundary ways or nodes'
        degrees = Counter(n for ref in refs for n in way_ends[ref])
        if any(n != 2 for n in degrees.values()): return 'Open or branching boundary rings'
        return None
    if completeness(country_id): raise ValueError('Incomplete Iraq boundary: '+completeness(country_id))
    if country_id not in areas: raise ValueError('Iraq country boundary incomplete')
    country = areas[country_id]
    governors = []
    # Foreign admin-4 boundaries may occur at the extract edge. Classify using
    # explicit ISO prefix, country subarea membership, or polygon containment.
    subareas = {ref for kind,ref,role in countries[country_id][1] if kind=='r' and role=='subarea'}
    for rid,(tags,members) in sorted(candidates.items()):
        code = tags.get('ISO3166-2','')
        poly = areas.get(rid)
        if code and not code.startswith('IQ-'): continue
        belongs = code.startswith('IQ-') or rid in subareas or (poly is not None and country.covers(poly.representative_point()))
        if not belongs:
            if poly is None and not code:
                errors.append({'relationId':rid,'error':'Unresolved admin-4 without country/ISO identity'})
            continue
        problem = completeness(rid)
        if problem or poly is None:
            errors.append({'relationId':rid,'name':tags.get('name'), 'error':problem or 'Incomplete boundary; no assembled area'})
            continue
        try: ident = tile_id(rid,tags)
        except ValueError as exc:
            errors.append({'relationId':rid,'error':str(exc)}); continue
        governors.append(dict(id=ident,relationId=rid,nameAr=tags.get('name:ar',tags.get('name','')),
                              geometry=mapping(poly)))
    ids = [g['id'] for g in governors]
    if len(ids) != len(set(ids)): errors.append({'error':'Duplicate governorate ISO identifiers'})
    governors.sort(key=lambda g:g['id'])
    with osmium.io.Reader(str(path)) as reader:
        snapshot = timestamp_ms(reader.header().get('osmosis_replication_timestamp'))
    return dict(snapshot=snapshot,governorates=governors,errors=errors,
                expectedGovernorates=19, governorateCount=len(governors),
                governorateCountWarning=None if len(governors)==19 else f'Expected 19, found {len(governors)}')


def projected_boundary(governorate):
    from shapely.geometry import shape, mapping
    from shapely.ops import transform
    from pyproj import CRS, Transformer
    poly = shape(governorate['geometry'])
    if poly.is_empty or not poly.is_valid or poly.geom_type not in ('Polygon','MultiPolygon'):
        raise ValueError('Invalid governorate polygon')
    c = poly.centroid
    metric = CRS.from_proj4(f'+proj=aeqd +lat_0={c.y} +lon_0={c.x} +datum=WGS84 +units=m')
    forward = Transformer.from_crs('EPSG:4326',metric,always_xy=True).transform
    reverse = Transformer.from_crs(metric,'EPSG:4326',always_xy=True).transform
    projected = transform(forward,poly)
    # Buffering is done in metres, never in degrees or a guessed rectangle.
    buffered = transform(reverse,projected.buffer(3000))
    simple = transform(reverse,projected.simplify(200,preserve_topology=True))
    if not simple.is_valid: raise ValueError('Simplification invalidated boundary')
    geo = mapping(simple)
    # Flat polygon field remains for single-ring clients. Multiple islands and
    # holes MUST be read from polygonGeometry; never flatten them to a bbox.
    rings = geo['coordinates'] if geo['type']=='Polygon' else geo['coordinates'][0]
    return buffered, dict(polygon=[list(p) for p in rings[0]], polygonGeometry=geo,
                          bbox=list(poly.bounds), polygonCoordinates='lon,lat',
                          bufferMeters=3000, simplificationMeters=200)


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('pbf',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=extract(a.pbf)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ('snapshot','governorateCount','governorateCountWarning','errors')},ensure_ascii=False))
    print(json.dumps([{'id':g['id'],'name':g['nameAr']} for g in result['governorates']],ensure_ascii=False))
    if result['errors'] or not result['governorates']: raise SystemExit('Incomplete boundaries; publication blocked')
