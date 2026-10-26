import contextlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from graph_builder import classify, build, Way, CAR, WALK, PENALTY, ACCESS_NO, ACCESS_PRIVATE
from inspect_graph import inspect
from inspect_near import near, segment_distance
from resolve_region import is_karbala_candidate, resolve
from install_ci_dependencies import select_osmium

BBOX = [0., 0., .1, .1]


class ContinueTest(unittest.TestCase):
    def test_walk_car_grant_default_speed_and_penalty(self):
        for highway in ("footway", "path", "pedestrian", "corridor"):
            _, flags, speed = classify({"highway": highway, "motor_vehicle": "yes"})
            self.assertEqual(speed, 15)
            self.assertEqual(flags & (CAR | WALK | PENALTY), CAR | WALK | PENALTY)
            self.assertEqual(classify({"highway": highway})[2], 5)
            self.assertEqual(classify({"highway": highway, "motor_vehicle": "yes", "maxspeed": "10"})[2], 10)

    def test_explicit_no_distinct_from_private_and_unknown_in_binary(self):
        for mode in ("access", "vehicle", "motor_vehicle", "motorcar"):
            for value in ("no", "private", "unknown"):
                tags = {"highway": "residential", mode: value}
                data, _, report = build({1: (.01, .01), 2: (.01, .02)},
                    [Way(1, (1, 2), tags)], [], "test", BBOX, 1)
                flags = inspect(data)["edges"][0][7]
                self.assertFalse(flags & CAR)
                self.assertTrue(flags & ACCESS_PRIVATE)
                self.assertEqual(bool(flags & ACCESS_NO), value == "no")
                self.assertEqual(report["explicitNoEdges"], int(value == "no"))
        # Vehicle-specific permission legally overrides generic access=no.
        flags = classify({"highway": "footway", "access": "no", "motorcar": "yes"})[1]
        self.assertTrue(flags & CAR)
        self.assertFalse(flags & ACCESS_NO)

    def test_report_counts_and_longest_ten(self):
        nodes = {i: (.01, .001*i) for i in range(1, 25)}
        ways = [Way(i, (i, i+1), {"highway": "residential", "name": str(i)}) for i in range(1, 21)]
        ways += [Way(30, (21, 22), {"highway": "footway"}),
                 Way(31, (22, 23), {"highway": "footway", "motor_vehicle": "yes"}),
                 Way(32, (23, 24), {"highway": "residential", "junction": "roundabout"})]
        _, _, report = build(nodes, ways, [], "test", BBOX, 1)
        self.assertEqual(report["walkEdges"], 2)
        self.assertEqual(report["walkEdgesWithCarGrant"], 1)
        self.assertEqual(report["onewayEdges"], 1)
        self.assertEqual(report["roundaboutEdges"], 1)
        self.assertAlmostEqual(report["namedCarEdgesRatio"], 20/22)
        longest = report["longestCarEdges"]
        self.assertEqual(len(longest), 10)
        self.assertEqual([r["lengthM"] for r in longest], sorted((r["lengthM"] for r in longest), reverse=True))
        self.assertNotIn(30, [r["osmWayId"] for r in longest])

    def test_near_uses_shape_not_only_endpoints_and_preserves_attributes(self):
        data, _, _ = build({1: (.01, .01), 2: (.01, .03), 3: (.02, .01), 4: (.02, .03)},
                          [Way(10, (1, 2), {"highway": "footway", "oneway": "-1", "name": "Test"}),
                           Way(20, (3, 4), {"highway": "residential"})], [], "test", BBOX, 1)
        rows = near(inspect(data), .01, .02, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["osmWayId"], 10)
        self.assertEqual(rows[0]["direction"], "backward")
        self.assertEqual(rows[0]["name"], "Test")
        self.assertEqual(rows[0]["distanceM"], 0)
        self.assertIn("WALK", rows[0]["flags"])
        self.assertFalse(rows[0]["carAllowed"])
        self.assertEqual(near(inspect(data), .08, .08, 1), [])
        with self.assertRaises(ValueError): near(inspect(data), .01, .02, -1)

    def test_near_curved_geometry_and_degenerate_segment(self):
        data, _, _ = build({1: (.01, .01), 2: (.02, .02), 3: (.01, .03)},
                          [Way(1, (1, 2, 3), {"highway": "residential"})], [], "test", BBOX, 1)
        graph = inspect(data)
        self.assertEqual(near(graph, .02, .02, 1)[0]["distanceM"], 0)
        self.assertEqual(near(graph, .01, .02, 1), [])
        self.assertEqual(segment_distance(.01, .01, (100000, 100000), (100000, 100000)), 0)

    def test_region_candidates_match_names_but_not_city_level(self):
        tags = {"boundary": "administrative", "admin_level": "4", "name": "محافظة كربلاء"}
        self.assertTrue(is_karbala_candidate(tags))
        self.assertTrue(is_karbala_candidate({**tags, "name": "KARBALA"}))
        self.assertFalse(is_karbala_candidate({**tags, "admin_level": "6"}))
        self.assertFalse(is_karbala_candidate({**tags, "name": "Other"}))

    def test_missing_region_reports_candidates_and_stops_before_geometry(self):
        class Handler:
            def apply_file(self, _):
                self.relation(SimpleNamespace(id=77, tags={"boundary": "administrative", "admin_level": "4", "name": "Karbala", "ISO3166-2": "unmatched"}))
        fake = SimpleNamespace(SimpleHandler=Handler)
        out = io.StringIO()
        with patch.dict(sys.modules, {"osmium": fake}), contextlib.redirect_stderr(out):
            with self.assertRaisesRegex(ValueError, "found 0"):
                resolve("unused", {"boundary_tag": "ISO3166-2", "boundary_value": "IQ-KA", "admin_level": "4"})
        self.assertEqual(json.loads(out.getvalue())["karbalaAdmin4Candidates"][0]["osmRelationId"], 77)

    def test_dependency_fallback_is_stable_four_x_and_ignores_yanked(self):
        self.assertEqual(select_osmium({"4.3.0": [{}], "4.9.0": [{}]}), "4.3.0")
        self.assertEqual(select_osmium({"4.3.0": [{"yanked": True}], "4.2.0": [{}], "4.3.2": [{}], "5.0.0": [{}], "4.4.0rc1": [{}]}), "4.3.2")
        with self.assertRaises(ValueError): select_osmium({"5.0.0": [{}], "4.3.0": []})

    def test_boundary_subarea_allowed_but_nested_outer_rejected(self):
        members = [SimpleNamespace(type="w", ref=1, role="outer"),
                   SimpleNamespace(type="r", ref=2, role="subarea")]
        class Handler:
            def apply_file(self, _, **kwargs):
                if hasattr(self, "relation"):
                    self.relation(SimpleNamespace(id=1, tags={"boundary": "administrative", "admin_level": "4", "ISO3166-2": "IQ-KA"}, members=members))
                else:
                    points=[SimpleNamespace(lat=lat, lon=lon, location=SimpleNamespace(valid=lambda: True))
                            for lat, lon in ((.01, .01), (.02, .02))]
                    self.way(SimpleNamespace(id=1, nodes=points))
        class Reader:
            def __init__(self, _): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def header(self): return {"osmosis_replication_timestamp": "2026-01-01T00:00:00Z"}
        fake = SimpleNamespace(SimpleHandler=Handler, io=SimpleNamespace(Reader=Reader))
        config={"boundary_tag": "ISO3166-2", "boundary_value": "IQ-KA", "admin_level": "4", "margin_m": 5000}
        with patch.dict(sys.modules, {"osmium": fake}):
            result=resolve("unused", config)
            self.assertLess(result["bbox"][0], .01)
            self.assertGreater(result["bbox"][2], .02)
            members[1].role="outer"
            with self.assertRaisesRegex(ValueError, "Nested boundary"):
                resolve("unused", config)


if __name__ == "__main__":
    unittest.main()
