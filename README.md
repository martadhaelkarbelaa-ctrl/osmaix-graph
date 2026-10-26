# OSMAIX Iraq road graph

Public OSM-derived map builder only. No application source, keys, home locations,
GPS tracks, user zones or personal overlays belong in this repository.

Data: © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright).
Source: one Geofabrik Iraq snapshot per run. `graph.yml` runs Fridays 03:00 UTC
and manually. Run **Build Iraq road tiles** with **verify_determinism=true** for
initial acceptance. Heavy PBF processing runs in GitHub Actions, not locally.

Output: one backbone (major Iraq roads, plus tertiary if <=60 MB including ALT)
and a detailed tile per admin-level-4 governorate, including a 3 km overlap.
No hard-coded governorate list. ISO3166-2 is used when present; otherwise the
actual OSM relation ID. Unexpected count is reported; incomplete boundaries fail.

Dated releases `graph-iraq-YYYYMMDD` contain compressed tiles, manifest and report.
`graph-latest` is advanced only after all dated assets are uploaded. Dated assets
are immutable. A failed partial draft must be removed or completed by the owner
before retrying the same date; no active release files are silently overwritten.

Compression: gzip -9, supported by Android without additional libraries.

```
python3 -m unittest discover -s tools/graph_builder/tests -v
```

Standard-library tests run locally. Four geometry integration tests require
Shapely and pyproj; CI installs them and rejects ANY skipped tests. See
[FORMAT.md](tools/graph_builder/FORMAT.md) for the v1/v2 wire format, ALT rounding
and unified-network heuristic caveat, topology and coordinate conventions.
See [VERIFICATION_070.md](VERIFICATION_070.md) for proven status and remaining gates.

Private road inspection (local only, coordinates supplied at runtime):

```
python tools/graph_builder/inspect_near.py LAT LON RADIUS_METRES tile.osmxg
```

Do not upload inspection output to this public repository or its releases.
