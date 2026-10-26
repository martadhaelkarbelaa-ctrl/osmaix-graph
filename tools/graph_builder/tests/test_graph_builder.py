import hashlib
import json
from pathlib import Path
import random
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from graph_builder import (build, classify, read_osm, Way, Relation, CAR, WALK, PENALTY,
                           ACCESS_PRIVATE, DESTINATION_ONLY, ONEWAY_FWD, ONEWAY_BACK,
                           ROUNDABOUT, TRACK, CLASSES, _cells)
from inspect_graph import inspect

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures"
BBOX = [32.59, 44., 32.62, 44.04]
EPOCH = 1767225600000


def fixture():
    return build(*read_osm(FIXTURE / "tiny.osm"), "tiny", BBOX, EPOCH)


def small(restrictions=(), tags=None):
    nodes = {1: (32.6, 44.01), 2: (32.6, 44.011), 3: (32.6, 44.012), 4: (32.601, 44.011)}
    ways = [Way(10, (1, 2, 3), tags or {"highway": "residential"}),
            Way(20, (2, 4), {"highway": "residential"})]
    return build(nodes, ways, restrictions, "test", BBOX, EPOCH)


class GraphBuilderTest(unittest.TestCase):
    def test_car_access_rules_all_highway_classes(self):
        for klass in CLASSES:
            flags = classify({"highway": klass})[1]
            self.assertEqual(bool(flags & CAR), CLASSES.index(klass) < 16, klass)
        for omitted in ("construction", "proposed", "abandoned", "raceway", "platform", "bus_guideway", "unknown"):
            self.assertIsNone(classify({"highway": omitted}))
        for mode in ("motorcar", "motor_vehicle", "vehicle", "access"):
            for value in ("no", "private", "agricultural", "forestry"):
                flags = classify({"highway": "residential", mode: value})[1]
                self.assertFalse(flags & CAR); self.assertTrue(flags & ACCESS_PRIVATE)
        self.assertTrue(classify({"highway": "residential", "access": "destination"})[1] & DESTINATION_ONLY)

    def test_access_precedence_and_explicit_car_permission(self):
        for mode in ("motorcar", "motor_vehicle", "vehicle"):
            for permission in ("yes", "permissive", "designated"):
                flags = classify({"highway": "footway", mode: permission, "access": "no"})[1]
                self.assertTrue(flags & CAR); self.assertTrue(flags & WALK)
        self.assertFalse(classify({"highway": "footway", "access": "yes"})[1] & CAR)
        self.assertFalse(classify({"highway": "footway", "motorcar": "no", "motor_vehicle": "yes"})[1] & CAR)
        self.assertFalse(classify({"highway": "residential", "access": "customers"})[1] & CAR)

    def test_oneway_variants(self):
        for value in ("yes", "true", "1"):
            self.assertTrue(classify({"highway": "residential", "oneway": value})[1] & ONEWAY_FWD)
        for value in ("-1", "reverse"):
            self.assertTrue(classify({"highway": "residential", "oneway": value})[1] & ONEWAY_BACK)
        for tags in ({"highway": "motorway"}, {"highway": "motorway_link"},
                     {"highway": "residential", "junction": "roundabout"},
                     {"highway": "residential", "junction": "circular"}):
            self.assertTrue(classify(tags)[1] & ONEWAY_FWD)
            self.assertFalse(classify({**tags, "oneway": "no"})[1] & (ONEWAY_FWD | ONEWAY_BACK))
        self.assertFalse(classify({"highway": "residential", "oneway": "reversible"})[1] & CAR)

    def test_speeds_and_penalty_subtype_preserved(self):
        self.assertEqual(classify({"highway": "primary", "maxspeed": "200"})[2], 120)
        self.assertEqual(classify({"highway": "primary", "maxspeed": "30 mph"})[2], 48)
        self.assertEqual(classify({"highway": "primary", "junction": "roundabout"})[2], 35)
        for subtype in ("parking_aisle", "driveway"):
            graph = inspect(small(tags={"highway": "service", "service": subtype})[0])
            for e in graph["edges"]:
                if e[-1] == 10:
                    self.assertEqual(e[6], 23); self.assertTrue(e[7] & PENALTY)

    def test_split_at_shared_nodes_preserves_geometry(self):
        data, manifest, _ = small()
        graph = inspect(data, manifest)
        self.assertEqual(len(graph["nodes"]), 4)
        self.assertEqual(len(graph["edges"]), 3)
        self.assertEqual([e[-1] for e in graph["edges"]], [10, 10, 20])
        nodes = {1: (32.6, 44.01), 2: (32.6, 44.011), 3: (32.6, 44.012)}
        graph = inspect(build(nodes, [Way(1, (1, 2, 3), {"highway": "residential"})], [], "test", BBOX, EPOCH)[0])
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(graph["edges"][0][3], 3)

    def test_restrictions_no_and_only(self):
        for typ in ("no_right_turn", "only_right_turn"):
            r = Relation(1, (("w", 10, "from"), ("n", 2, "via"), ("w", 20, "to")), {"type": "restriction", "restriction": typ})
            graph = inspect(small([r])[0])
            self.assertTrue(graph["restrictions"])
            for a, via, b, _ in graph["restrictions"]:
                self.assertEqual(graph["edges"][a][-1], 10)
                self.assertEqual(graph["nodes"][via], (326000000, 440110000))
                self.assertEqual(graph["edges"][b][-1] == 20, typ.startswith("no_"))

    def test_no_u_turn_does_not_block_straight_continuation(self):
        r = Relation(1, (("w", 10, "from"), ("n", 2, "via"), ("w", 10, "to")), {"restriction": "no_u_turn"})
        graph = inspect(small([r])[0])
        self.assertEqual(len(graph["restrictions"]), 2)
        self.assertTrue(all(a == b for a, _, b, _ in graph["restrictions"]))

    def test_via_way_restrictions_reported_not_applied(self):
        r = Relation(1, (("w", 10, "from"), ("w", 20, "via"), ("w", 10, "to")), {"restriction": "no_left_turn"})
        data, _, report = small([r])
        self.assertEqual(inspect(data)["restrictions"], [])
        self.assertEqual(report["ignoredRestrictionRelations"], {"via_way": 1})

    def test_conditional_and_car_exempt_are_reported(self):
        members = (("w", 10, "from"), ("n", 2, "via"), ("w", 20, "to"))
        for tags, reason in (({"restriction": "no_right_turn", "except": "motorcar"}, "car_exempt"),
                             ({"restriction:conditional": "no_right_turn @ (Mo-Fr)"}, "conditional")):
            data, _, report = small([Relation(1, members, tags)])
            self.assertEqual(inspect(data)["restrictions"], [])
            self.assertEqual(report["ignoredRestrictionRelations"], {reason: 1})

    def test_deterministic_output_with_shuffled_input(self):
        nodes, ways, relations = read_osm(FIXTURE/"tiny.osm")
        reference = build(nodes, ways, relations, "tiny", BBOX, EPOCH)
        rng = random.Random(70)
        for _ in range(20):
            rng.shuffle(ways); rng.shuffle(relations)
            items = list(nodes.items()); rng.shuffle(items)
            self.assertEqual(build(dict(items), ways, relations, "tiny", BBOX, EPOCH), reference)

    def test_tiny_fixture_matches_committed(self):
        data, manifest, report = fixture()
        self.assertEqual(data, (FIXTURE/"tiny.osmxg").read_bytes())
        self.assertEqual(manifest, json.loads((FIXTURE/"manifest.json").read_text()))
        self.assertEqual(report, json.loads((FIXTURE/"report.json").read_text()))

    def test_crc_and_sha_fail_closed(self):
        data, manifest, _ = fixture()
        inspect(data, manifest)
        for pos in (0, 8, len(data)//2, len(data)-1):
            broken = bytearray(data); broken[pos] ^= 1
            with self.assertRaises(ValueError): inspect(broken)
            with self.assertRaises(ValueError): inspect(broken, manifest)
        with self.assertRaises(ValueError): inspect(data, {**manifest, "sha256": "0"*64})
        with self.assertRaises(ValueError): inspect(data, {**manifest, "regionId": "wrong"})
        with self.assertRaises(ValueError): inspect(data, {**manifest, "formatVersion": 2})

    def test_truncation_and_extra_bytes_fail_closed_even_with_new_crc(self):
        data = fixture()[0]
        for pos in (20, 60, 100, len(data)-20):
            shortened = data[:pos]
            shortened += struct.pack("<I", zlib.crc32(shortened))
            with self.assertRaises((ValueError, UnicodeError)): inspect(shortened)
        extra = data[:-4]+b"extra"
        extra += struct.pack("<I", zlib.crc32(extra))
        with self.assertRaises(ValueError): inspect(extra)

    def test_invalid_counts_fail_before_allocating(self):
        data = bytearray(fixture()[0])
        count_offset = 8+2+2+len("tiny")+16+16
        struct.pack_into("<I", data, count_offset, 0xffffffff)
        struct.pack_into("<I", data, len(data)-4, zlib.crc32(data[:-4]))
        with self.assertRaises(ValueError): inspect(data)

    def test_spatial_grid_includes_middle_of_long_segments(self):
        cells = set(_cells((.1, .1), (4.9, .1)))
        self.assertTrue({i << 32 for i in range(5)} <= cells)
        diagonal = set(_cells((.1, .1), (4.9, 4.9)))
        self.assertTrue({(i << 32) | i for i in range(5)} <= diagonal)
        boundary = set(_cells((0., 0.), (0., 2.)))
        self.assertIn(1, boundary)
        self.assertIn(-4294967295, boundary)

    def test_missing_nodes_and_invalid_bbox_fail(self):
        with self.assertRaises(ValueError):
            build({1: (32.6, 44.01)}, [Way(1, (1, 2), {"highway": "residential"})], [], "x", BBOX, EPOCH)
        with self.assertRaises(ValueError):
            build({}, [], [], "x", [40, 40, 30, 50], EPOCH)

    def test_arabic_name_and_ref_are_distinct(self):
        graph = inspect(small(tags={"highway": "residential", "name:ar": "شارع النقيب", "name": "English", "ref": "84"})[0])
        e = graph["edges"][0]
        self.assertEqual(graph["names"][e[8]], "شارع النقيب")
        self.assertEqual(graph["names"][e[9]], "84")


if __name__ == "__main__":
    unittest.main()
