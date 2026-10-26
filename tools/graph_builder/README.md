# Immutable regional road graph

Stage 1 implementation for OSMAIX 0.7.0. This tool does not change Android
routing until the subsequent integration stages have passed acceptance.

Fixture build (standard library only):

```sh
python3 tools/graph_builder/graph_builder.py tools/graph_builder/fixtures/tiny.osm \
  --region tiny --bbox 32.59 44.00 32.62 44.04 \
  --source-timestamp 1767225600000 --output /tmp/osmaix-tiny
python3 -m unittest discover -s tools/graph_builder/tests -v
```

The same tests are pytest-compatible. Dependency installation and PBF/Android
builds run ONLY in GitHub Actions for this project. The following commands
are CI instructions, not commands to run in the agent environment:

```sh
python3 -m pip install -r tools/graph_builder/requirements.txt
python3 -m pytest tools/graph_builder/tests
```

For the current Iraq workflow, use one PBF snapshot and extract complete admin-4
polygons. Build national topology once, select the backbone and its directed ALT
tables, and intersect full edge geometry with each polygon buffered by 3 km.
Write v2 tiles, validate their structure and raw/compressed hashes, and perform
the requested same-snapshot deterministic rebuild before publication. Missing
or nested boundary geometry blocks publication; bounding boxes are not substitutes.
The published payload is exclusively OSM-derived. Private overlays and GPS
traces never enter this pipeline.

`inspect_graph.inspect` checks corruption and structural consistency; it does
not certify that every real-world road/traffic rule exists in OSM. A successful
fixture test is not a successful Karbala build or an Android performance test.
The archive's VERIFICATION_070.md records exactly which checks ran.


Continuation changes: WALK+CAR uses 15 km/h and PENALTY; ACCESS_NO preserves
an explicit legal prohibition for future manual-only changes. Full production
verification requires the public graph workflow and recorded Actions evidence.
`inspect_near.py LAT LON RADIUS GRAPH` is for local diagnosis after downloading
a verified graph artifact. Do not put its personal inputs/output in CI or git.
