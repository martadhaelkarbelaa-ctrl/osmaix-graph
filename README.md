# OSMAIX public road graphs

This repository contains only the graph builder, synthetic fixtures and the
workflow for generating regional road data from OpenStreetMap. The Android
application belongs in the separate private osmaix-navigation repository.

Generated geographic databases are distributed under the Open Data Commons
Open Database License (ODbL 1.0): https://opendatacommons.org/licenses/odbl/1-0/
Attribution: © OpenStreetMap contributors, https://www.openstreetmap.org/copyright
OSM input: https://download.geofabrik.de/asia/iraq-latest.osm.pbf

Friday 03:00 UTC or manual graph.yml dispatch builds the Karbala governorate
region plus a 5 km margin from its actual boundary in the input PBF. A missing
boundary fails with diagnostic candidates; no guessed coverage is published.

Releases: graph-karbala-YYYYMMDD contains the database, manifest, hash and
report; graph-latest contains the latest manifest. Files are unsigned data,
verified by SHA-256, CRC and structural checks over HTTPS. The app contains
no GitHub credentials. Inspect report.json for unsupported OSM restrictions.
No completed release is claimed until a successful Actions run is recorded.

No personal GPS, home locations, restrictions, access permits, overlays or
signing keys may be committed here. inspect_near.py is a private local CLI;
never run it with personal coordinates in Actions or commit its output.

The ODbL notice applies to geographic data, not a blanket software-license
grant. Publishing the source does not authorize collecting personal data.

See tools/graph_builder/README.md and FORMAT.md for the build contract.
