# Synthetic v2 compatibility fixtures

`backbone.osmxg`, `gov-osm-r9001.osmxg`, `gov-osm-r9002.osmxg` are generated
from `tests/test_iraq_v2.py:tiles()`. The deterministic fixture test regenerates
and compares every byte. Coordinates near the equator are synthetic.

Two adjoining test areas share overlap edges and OSM node IDs. The backbone
omits an only-turn allowed local exit, while retaining the resulting prohibited
backbone transition. It also contains direction-aware ALT tables. The detailed
tiles include a car-granted footway and an ordinary WALK edge.

These files are ONLY test data, never usable navigation maps.
