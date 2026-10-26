# Iraq stage A verification — 2026-10-27 Baghdad

## Owner input / gates

No signing key is needed or requested. Real graph acceptance requires an Actions
run with verify_determinism=true. Remote execution status will be recorded after
publication. No Android stage 2 work may start before stage A is accepted.

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

## Implemented but awaiting Actions integration tests

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

- No real Iraq tile, actual governorate count, size, or real network connectivity
  has been measured yet. No run/release success is claimed without a remote run.
- Private alley diagnosis awaits real gov-iq-ka. It must remain local/private.
- Android stages 2–9, TileManager, unified router, UI and field tests remain
  unimplemented. Original app remains com.osmaix.navigation, versionCode 56.
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
