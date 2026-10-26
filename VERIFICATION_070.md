# Iraq stage A verification — 2026-10-27 Baghdad

## Owner input / gates

No signing key is needed or requested. Stage A is blocked by source boundary
relation 21118515. Run 40419489184 found 19 complete governorates plus that
unresolved admin-4 relation, and failed before map building/publication. Keep the
strict boundary gate. Source correction followed by a new Geofabrik snapshot, or
an explicit revised owner policy for this anomalous relation, is needed to unblock.
No new Iraq-dependent Android integration may start before stage A is accepted.

## Implemented and tested locally

- Recovered graph-only history from the existing checkpoint bundle.
- National topology is split once, then subset to tiles; v2 stores stable OSM
  node identity, portal flags, tile metadata, snapshot and directed ALT tables.
- v1 fixture/read compatibility, v2 round-trip, corruption checks, overlap IDs,
  only-turn preservation when the permitted local exit is absent, directed ALT
  admissibility including floor-seconds correction, reproducibility, gzip/raw
  hashes, explicit CAR grants on footways, and strict timestamp/ID validation.
- `python3 -m unittest discover -s tools/graph_builder/tests -v`: 43 discovered,
  39 passed, 4 skipped because Shapely/pyproj are absent locally. No failure.
- `python3 -m compileall -q tools/graph_builder`: successful.
- No PBF/map data downloaded and no Android build performed in this executor.

## Actions evidence

- Commit aaa9c8927c8a6ee7d491470ea20d4a4784d57c2d, run
  https://github.com/martadhaelkarbelaa-ctrl/osmaix-graph/actions/runs/40419489184
- All 43 tests passed, including all four Shapely/pyproj integration tests.
- One Iraq PBF was downloaded in Actions: 91,307,126 bytes; header snapshot
  2026-10-25T21:21:21Z (1792963281000).
- 19 complete governorates found, including Halabja (osm-r3826029).
- Boundary validation failed on relation 21118515. No Iraq graph/release was
  published and graph-latest was not changed by this run.
- Verification artifact: iraq-graph-verification-40419489184, ID 12697417069.
- Live OSM API inspection found the relation named "حدود حي الامين", admin_level=4,
  with only subarea relation 21118480 and label node 14027644388; no outer ways.
  Its child is tagged admin_level=8.
- Diagnostic run 40419993981 at commit 2ca79d590fb65735ed2e1ba18ca02eb45b3a20f9
  confirmed the exact same tags and members from the PBF snapshot; geometryError
  is "Boundary has no outer ways". All 43 tests passed in 0.62s, then the boundary
  gate failed as required. Artifact ID 12697287970 (397,611 bytes):
  https://github.com/martadhaelkarbelaa-ctrl/osmaix-graph/actions/runs/40419993981
- graph-latest still contains its original manifest updated 2026-10-26T22:36:39Z;
  neither Iraq run reached the release publication step.

## Implemented but awaiting real national build verification

- PBF boundaries from actual Iraq/admin4 relations; invalid, missing or nested
  geometry fails closed. Actual count/names recorded, not forced to 19.
- 3km metric buffer, exact geometry intersection, 200m topology-preserving
  manifest polygons with holes and islands retained in polygonGeometry.
- Backbone variants measured with/without tertiary, 16 farthest landmarks,
  connectivity gate >=0.98, per-governorate reports and component explanations.
- Same-snapshot deterministic rebuild, compression and size validation, dated
  immutable releases, graph-latest updated only after successful publication.
- Four geometry integration tests are explicitly enforced (no skips) in CI.

## Not implemented / not verified

- No real Iraq tile sizes, ALT, determinism, or backbone connectivity have been
  measured: extraction failed before those stages. Governorate count was measured.
- Private alley diagnosis awaits real gov-iq-ka. It must remain local/private.
- The remote private app branch update/070 already contains earlier v1/Karbala
  stages 2–4 at 5c76e8ea13a067e8b574ded7c72d7aceda769bff; stage-4 run
  40417996096 passed. This was discovered after the older local checkpoint was
  recovered. That newer branch has not been overwritten or modified here.
- Iraq v2 TileManager/unified routing integration and later app stages remain
  pending. Original app identity/signing/version have not been changed here.
- No APK, certificate, new key, migration, phone performance, or field result.

## Design notes for the next stage

Backbone ALT distances alone are not admissible when detailed governorate
shortcuts are searchable, even without a personal road. The future unified
router must disable that bound or compute a valid relaxed unified bound. Do not
silently take max(backbone ALT, geometric bound) on a graph that has new edges.
Subtract one second from directed ALT differences of independently floored u32
seconds, excluding INF, to preserve admissibility.

Binary bbox keeps the national grid reference frame. Manifest geography uses
lon/lat GeoJSON and must use polygonGeometry for holes or disconnected islands.
Raw/overlap counts are storage totals. Via-way and conditional restrictions remain
reported limitations, not enforced restrictions.
