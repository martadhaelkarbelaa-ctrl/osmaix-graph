import copy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from graph_builder import Way, Relation, build, CAR, WALK, PENALTY
from graph_v2 import subset, encode, alt_tables, alt_bound, adjacency, distances, summary
from inspect_graph import inspect
from build_iraq import national_graph, write_tile, build_atlas, compare_outputs
from iraq_boundaries import tile_id, metadata_error, timestamp_ms

GEOMETRY = all(importlib.util.find_spec(n) for n in ('shapely','pyproj'))
FIXTURE = Path(__file__).resolve().parents[1]/'fixtures'/'tiny_v2'


def inputs():
    # Synthetic geography near the equator, never real user GPS or travel data.
    nodes={i:(.02,(i-1)*.01) for i in range(1,9)}
    nodes.update({101:(.03,.02),102:(.04,.02),103:(.03,.05),104:(.04,.05)})
    ways=[Way(10,(1,2,3,4,5,6,7,8),{'highway':'primary','name':'Synthetic main'}),
          Way(11,(3,101,102),{'highway':'residential'}),
          Way(12,(6,103,104),{'highway':'footway','motor_vehicle':'yes'}),
          Way(13,(101,103),{'highway':'residential','oneway':'yes'}),
          Way(14,(102,104),{'highway':'footway'}),
          Way(15,(4,103),{'highway':'tertiary'}),
          Way(16,(2,101),{'highway':'service','access':'private'})]
    relations=[Relation(1000,(('w',10,'from'),('n',3,'via'),('w',11,'to')),
                        {'type':'restriction','restriction':'only_right_turn'})]
    return nodes,ways,relations


def tiles():
    graph,_,_=national_graph(*inputs(),1000)
    rows=[i for i,e in enumerate(graph['edges']) if e[10] in (10,15)]
    backbone=subset(graph,rows,'backbone',0);backbone['nodeFlags']=[1]*len(backbone['nodes'])
    backbone['landmarks']=alt_tables(backbone)
    # Overlapping 3km margins around two touching synthetic polygons.
    def in_tile(edge,low,high):
        p=graph['geometry'][edge[2]:edge[2]+edge[3]]
        return min(x[1]/1e7 for x in p)<=high and max(x[1]/1e7 for x in p)>=low
    west=[i for i,e in enumerate(graph['edges']) if in_tile(e,-.01-.02698,.035+.02698)]
    east=[i for i,e in enumerate(graph['edges']) if in_tile(e,.035-.02698,.08+.02698)]
    return [backbone,subset(graph,west,'gov-osm-r9001',1,backbone['osmNodeIds']),
            subset(graph,east,'gov-osm-r9002',1,backbone['osmNodeIds'])]


class V2Test(unittest.TestCase):
    def test_v2_roundtrip(self):
        for g in tiles():
            d=inspect(encode(g))
            for key in ('nodes','osmNodeIds','nodeFlags','edges','geometry','restrictions','landmarks','tileId','snapshot'):
                self.assertEqual(g[key],d[key],key)

    def test_v2_portal_flags_match_backbone(self):
        bb,a,b=tiles();ids=set(bb['osmNodeIds'])
        for g in (a,b):
            self.assertEqual(g['nodeFlags'],[int(n in ids) for n in g['osmNodeIds']])

    def test_overlap_edge_identity_and_geometry(self):
        _,a,b=tiles()
        def edges(g):
            return {(e[10],g['osmNodeIds'][e[0]],g['osmNodeIds'][e[1]]):g['geometry'][e[2]:e[2]+e[3]] for e in g['edges']}
        aa,bb=edges(a),edges(b)
        self.assertTrue(aa.keys()&bb.keys())
        for key in aa.keys()&bb.keys(): self.assertEqual(aa[key],bb[key])

    def test_alt_tables_admissible(self):
        g=tiles()[0];adj,_=adjacency(g)
        for start in range(len(g['nodes'])):
            actual=distances(adj,start)
            for target in range(len(adj)):
                self.assertLessEqual(alt_bound(g,start,target),actual[target]+1e-9)

    def test_alt_direction_unreachable_and_fractional_rounding(self):
        g=tiles()[0]
        # Prohibit every reverse traversal, then verify directed bounds.
        g['edges']=[(*e[:7],(e[7]&~64)|32,*e[8:]) for e in g['edges']]
        g['landmarks']=alt_tables(g);adj,_=adjacency(g)
        for a in range(len(adj)):
            d=distances(adj,a)
            for b in range(len(adj)): self.assertLessEqual(alt_bound(g,a,b),d[b]+1e-9)
        self.assertTrue(any(0xffffffff in l['fromLandmark'] for l in g['landmarks']))

    def test_only_turn_survives_omitted_allowed_exit(self):
        bb=tiles()[0]
        self.assertTrue(bb['restrictions'])
        self.assertNotIn(11,{e[10] for e in bb['edges']})

    def test_manifest_hashes_compressed_and_raw(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);entry,_=write_tile(tiles()[0],path)
            raw=(path/entry['file']).read_bytes();compressed=(path/entry['compressed']['file']).read_bytes()
            self.assertEqual(gzip.decompress(compressed),raw)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),entry['sha256'])
            self.assertEqual(hashlib.sha256(compressed).hexdigest(),entry['compressed']['sha256'])
            inspect(raw,entry)

    def test_v2_corruption_and_manifest_mismatch(self):
        g=tiles()[0];data=bytearray(encode(g));data[-1]^=1
        with self.assertRaises(ValueError): inspect(data)
        good=encode(g)
        entry={'bytes':len(good),'sha256':hashlib.sha256(good).hexdigest(),'snapshot':999}
        with self.assertRaises(ValueError): inspect(good,entry)
        for flag in (2,255):
            bad=copy.deepcopy(g);bad['nodeFlags'][0]=flag
            with self.assertRaises(ValueError): inspect(encode(bad))
        bad=copy.deepcopy(g);bad['osmNodeIds'][1]=bad['osmNodeIds'][0]
        with self.assertRaises(ValueError): inspect(encode(bad))
        bad=copy.deepcopy(g);bad['landmarks'][0]['nodeRow']=len(bad['nodes'])
        with self.assertRaises(ValueError): inspect(encode(bad))

    def test_v2_deterministic_after_input_shuffle(self):
        n,w,r=inputs()
        g,_,_=national_graph(n,w,r,1000);h,_,_=national_graph(dict(reversed(list(n.items()))),w[::-1],r[::-1],1000)
        a=subset(g,range(len(g['edges'])),'all',1);b=subset(h,range(len(h['edges'])),'all',1)
        self.assertEqual(encode(a),encode(b))

    def test_committed_tiny_v2(self):
        for g in tiles(): self.assertEqual(encode(g),(FIXTURE/(g['tileId']+'.osmxg')).read_bytes())

    def test_footway_with_car_grant_speed_and_penalty(self):
        _,a,_=tiles();e=next(e for e in a['edges'] if e[10]==12)
        self.assertEqual(e[5],15);self.assertEqual(e[7]&(CAR|WALK|PENALTY),CAR|WALK|PENALTY)

    def test_boundary_ids_and_timestamp_are_not_guessed(self):
        self.assertEqual(tile_id(7,{}),'osm-r7');self.assertEqual(tile_id(7,{'ISO3166-2':'IQ-KA'}),'iq-ka')
        with self.assertRaises(ValueError): tile_id(7,{'ISO3166-2':'XX-ABC'})
        for v in ('',None,'2026-01-01T00:00:00'):
            with self.assertRaises(ValueError): timestamp_ms(v)
        self.assertEqual(timestamp_ms('1970-01-01T00:00:01Z'),1000)
        self.assertIsNotNone(metadata_error({},[('r',1,'outer')]))
        self.assertIsNotNone(metadata_error({},[]))
        self.assertIsNone(metadata_error({},[('w',2,'outer'),('r',3,'subarea')]))

    def test_summary_and_compression_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'a';b=Path(temp)/'b';a.mkdir();b.mkdir()
            write_tile(tiles()[0],a);write_tile(tiles()[0],b)
            self.assertTrue(compare_outputs(a,b)['identical'])
        r=summary(tiles()[0]);self.assertEqual(r['largestCarWeakComponentRatio'],1.)
        self.assertEqual(r['isolatedCarComponentsOver20'],[])


@unittest.skipUnless(GEOMETRY,'Shapely/pyproj are installed by GitHub Actions')
class GeometryTest(unittest.TestCase):
    def governorates(self):
        def gov(i,low,high):
            return dict(id=f'osm-r{i}',nameAr='Synthetic '+str(i),geometry={
                'type':'Polygon','coordinates':[[[low,0],[high,0],[high,.06],[low,.06],[low,0]]]})
        return dict(snapshot=1000,errors=[],governorates=[gov(9001,-.01,.035),gov(9002,.035,.08)])

    def test_governorate_overlap_margin(self):
        from iraq_boundaries import projected_boundary
        from shapely.geometry import Point
        a,b=[projected_boundary(g)[0] for g in self.governorates()['governorates']]
        self.assertTrue(a.intersects(b))
        self.assertTrue(a.covers(Point(.055,.02)))
        self.assertFalse(a.covers(Point(.075,.02)))
        self.assertTrue(b.covers(Point(.015,.02)))

    def test_atlas_polygon_cut_and_determinism(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'a';b=Path(temp)/'b'
            manifest,report=build_atlas(*inputs(),self.governorates(),a)
            n,w,r=inputs();build_atlas(n,w[::-1],r[::-1],self.governorates(),b)
            self.assertTrue(compare_outputs(a,b)['identical'])
            self.assertEqual(len(manifest['governorates']),2)
            self.assertTrue(report['files']['backbone']['tertiaryIncluded'])
            self.assertTrue(report['files']['backbone']['sizeComparison']['withoutTertiary']>0)
            bb=inspect((a/'backbone.osmxg').read_bytes())
            for e in manifest['governorates']:
                g=inspect((a/e['file']).read_bytes(),e)
                self.assertEqual(g['nodeFlags'],[int(n in set(bb['osmNodeIds'])) for n in g['osmNodeIds']])

    def test_holes_are_not_filled_by_bbox(self):
        from iraq_boundaries import projected_boundary
        from shapely.geometry import Point
        gov={'geometry':{'type':'Polygon','coordinates':[
            [[0,0],[1,0],[1,1],[0,1],[0,0]],
            [[.2,.2],[.2,.8],[.8,.8],[.8,.2],[.2,.2]]]}}
        buffered,meta=projected_boundary(gov)
        self.assertFalse(buffered.covers(Point(.5,.5)))
        self.assertEqual(len(meta['polygonGeometry']['coordinates']),2)

    def test_invalid_boundary_fails_closed(self):
        from iraq_boundaries import projected_boundary
        with self.assertRaises(ValueError):
            projected_boundary({'geometry':{'type':'Polygon','coordinates':[[[0,0],[1,1],[0,1],[1,0],[0,0]]]}})

if __name__=='__main__':unittest.main()
