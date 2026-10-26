"""Build one national snapshot into backbone and governorate v2 tiles.

Production invocation is Actions-only. Tiny synthetic input is allowed locally.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gc
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

from graph_builder import build, read_osm, CAR
from graph_v2 import subset, encode, summary, alt_tables
from inspect_graph import inspect
from iraq_boundaries import projected_boundary

BACKBONE_CLASSES = {0,1,2,3,5,6,7,8}
TERTIARY_CLASSES = BACKBONE_CLASSES | {4,9}


def json_write(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')


def write_tile(graph, out, compression='gzip'):
    data = encode(graph)
    file = out / (graph['tileId']+'.osmxg')
    entry = dict(file=file.name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                 tileId=graph['tileId'], formatVersion=2, snapshot=graph['snapshot'])
    # Structural validation before even writing a candidate.
    inspect(data,entry)
    file.write_bytes(data)
    if compression == 'gzip':
        compressed = file.with_suffix('.osmxg.gz')
        with compressed.open('wb') as target:
            with gzip.GzipFile(filename='',mode='wb',fileobj=target,compresslevel=9,mtime=0) as gz:
                gz.write(data)
    else:
        compressed = file.with_suffix('.osmxg.zst')
        subprocess.run(['zstd','-19','--threads=1','-f',str(file),'-o',str(compressed)],check=True)
    compressed_bytes = compressed.read_bytes()
    if len(compressed_bytes) >= 2_000_000_000 or len(data) >= 2_000_000_000:
        raise ValueError('Release file exceeds 2GB limit: '+file.name)
    entry['compressed'] = dict(file=compressed.name,bytes=len(compressed_bytes),
                               sha256=hashlib.sha256(compressed_bytes).hexdigest(),encoding=compression)
    report = summary(graph)
    report.update(bytes=len(data), compressedBytes=len(compressed_bytes), releaseAssetUnder2GB=True)
    return entry,report


def national_graph(nodes,ways,relations,snapshot):
    points=list(nodes.values())
    bbox=[min(p[0] for p in points),min(p[1] for p in points),
          max(p[0] for p in points),max(p[1] for p in points)]
    ids, audit = [], []
    data, _, report = build(nodes,ways,relations,'iraq',bbox,snapshot,
                           node_ids_out=ids,restriction_audit_out=audit)
    graph=inspect(data);graph['osmNodeIds']=ids
    return graph,report,dict(audit)


def restriction_report(graph, relations, audit):
    way_ids={e[10] for e in graph['edges']}
    relevant=[r for r in relations if any(kind=='w' and role in ('from','to','via') and ref in way_ids
                                        for kind,ref,role in r.members)]
    counts=Counter(audit[r.id] for r in relevant)
    return dict(appliedRestrictionRelations=counts.pop('applied',0),
                ignoredRestrictionRelations=dict(sorted(counts.items())),
                restrictionAccounting='National relation classification, limited to relations touching tile ways; prohibitedTurns is the actual serialized transition count')


def build_atlas(nodes,ways,relations,boundaries,out,compression='gzip',enforce_acceptance=True):
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    if boundaries.get('errors'): raise ValueError('Boundary errors block atlas build')
    if not boundaries['governorates']: raise ValueError('No governorates')
    snapshot=boundaries['snapshot'];out.mkdir(parents=True,exist_ok=True)
    graph, national_report, audit = national_graph(nodes,ways,relations,snapshot)
    # Build both with the SAME national cuts; compare full size including ALT.
    sizes={};chosen=None
    for include,classes in ((False,BACKBONE_CLASSES),(True,TERTIARY_CLASSES)):
        rows=[i for i,e in enumerate(graph['edges']) if e[6] in classes]
        candidate=subset(graph,rows,'backbone',0)
        candidate['nodeFlags']=[1]*len(candidate['nodes'])
        candidate['landmarks']=alt_tables(candidate)
        sizes['withTertiary' if include else 'withoutTertiary']=len(encode(candidate))
        if not include or sizes['withTertiary'] <= 60_000_000: chosen=candidate
    backbone_ids=set(chosen['osmNodeIds'])
    entry,report=write_tile(chosen,out,compression)
    report.update(restriction_report(chosen,relations,audit))
    report.update(sizeComparison=sizes, tertiaryIncluded=sizes['withTertiary']<=60_000_000)
    reports={'backbone':report};manifest=dict(formatVersion=2,snapshot=snapshot,backbone=entry,governorates=[])
    errors=[]
    if report['largestCarWeakComponentRatio'] < .98:
        errors.append('Backbone largestCarWeakComponentRatio below 0.98')
    del candidate,chosen
    gc.collect()
    # Index complete edge geometry once; no endpoint-only clipping, no bounding
    # box substitution. An edge can cross a governorate with both ends outside.
    shapes=[LineString([(p[1]/1e7,p[0]/1e7) for p in graph['geometry'][e[2]:e[2]+e[3]]])
            for e in graph['edges']]
    tree=STRtree(shapes)
    for gov in sorted(boundaries['governorates'],key=lambda g:g['id']):
        buffered,geography=projected_boundary(gov)
        rows=sorted(map(int,tree.query(buffered,predicate='intersects')))
        try:
            tile=subset(graph,rows,'gov-'+gov['id'],1,backbone_ids)
            e,r=write_tile(tile,out,compression)
            r.update(restriction_report(tile,relations,audit))
            e.update(id=gov['id'],nameAr=gov['nameAr'],**geography)
            manifest['governorates'].append(e);reports[e['tileId']]=r
        except ValueError as exc:
            errors.append(f"{gov['id']}: {exc}")
    report=dict(snapshot=snapshot,formatVersion=2,files=reports,errors=errors,
                governorateCount=len(manifest['governorates']),expectedGovernorates=19,
                governorateNames=[g['nameAr'] for g in manifest['governorates']],
                governorateCountWarning=boundaries.get('governorateCountWarning'),
                nationalRestrictionAccounting={k:national_report[k] for k in
                    ('appliedRestrictionRelations','ignoredRestrictionRelations','prohibitedTurns')},
                compression=compression,
                compressionDecision='gzip -9: Android java.util.zip.GZIPInputStream needs no added dependency' if compression=='gzip' else 'zstd -19',
                license='ODbL-1.0',attribution='© OpenStreetMap contributors',
                limitations=['Via-way and conditional restrictions are counted but not applied',
                    'ALT is a backbone-only lower bound, not automatically admissible across detailed or personal shortcuts. Router must use geometric bound or recompute a relaxed unified bound when such edges are searchable.',
                    'Each tile retains national grid origin and bbox; use manifest polygonGeometry to determine governorate coverage.'])
    report['totals']={k:sum(r[k] for r in reports.values()) for k in
                      ('bytes','compressedBytes','nodes','edges','walkEdges','onewayEdges','roundaboutEdges',
                       'walkEdgesWithCarGrant','accessPrivateEdges','prohibitedTurns')}
    report['totals']['includesOverlapDuplicates']=True
    json_write(out/'report.json',report)
    json_write(out/'manifest.json',manifest)
    if enforce_acceptance and errors: raise ValueError('; '.join(errors))
    return manifest,report


def release_urls(out,repository):
    manifest=json.loads((out/'manifest.json').read_text())
    date=datetime.fromtimestamp(manifest['snapshot']/1000,timezone.utc).strftime('%Y%m%d')
    tag='graph-iraq-'+date
    prefix=f'https://github.com/{repository}/releases/download/{tag}/'
    for e in [manifest['backbone'],*manifest['governorates']]:
        # Only compressed graphs are published; raw checksum verifies extraction.
        e['compressed']['downloadUrl']=prefix+e['compressed']['file']
    json_write(out/'manifest.json',manifest)
    return tag


def compare_outputs(first,second):
    names=sorted(p.name for p in first.iterdir() if p.suffix in ('.osmxg','.gz','.zst') or p.name in ('manifest.json','report.json'))
    other=sorted(p.name for p in second.iterdir() if p.suffix in ('.osmxg','.gz','.zst') or p.name in ('manifest.json','report.json'))
    if names != other: raise ValueError('Nondeterministic output inventory')
    for name in names:
        if (first/name).read_bytes() != (second/name).read_bytes():
            raise ValueError('Nondeterministic bytes: '+name)
    return dict(filesCompared=len(names),identical=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('pbf',type=Path);p.add_argument('--boundaries',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--verify-determinism',action='store_true')
    p.add_argument('--repository',required=True);a=p.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true': raise SystemExit('Real PBF build is reserved for GitHub Actions')
    boundaries=json.loads(a.boundaries.read_text())
    nodes,ways,relations=read_osm(a.pbf)
    build_atlas(nodes,ways,relations,boundaries,a.output)
    if a.verify_determinism:
        second=a.output.parent/(a.output.name+'-repeat')
        build_atlas(nodes,list(reversed(ways)),list(reversed(relations)),boundaries,second)
        json_write(a.output/'determinism.json',compare_outputs(a.output,second))
    tag=release_urls(a.output,a.repository)
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'],'a') as f: f.write('GRAPH_TAG='+tag+'\n')
    print(json.dumps(dict(tag=tag,manifest=str(a.output/'manifest.json'))))

if __name__=='__main__': main()
