# Iraq stage A verification — 2026-10-27 Baghdad

## Owner input / gates

No further owner decision is needed for the graph publication. The owner approved
excluding relation 21118515 only. Exact reviewed metadata is matched; different
IDs, new outer geometry, changed name or ISO return to normal strict validation.
The applied exception is recorded in boundaries.json and report.json.

## Implemented and verified in GitHub Actions

- Code commit: 625346938c0e20d20e173824de7ff56b4e00c224.
- Successful run: https://github.com/martadhaelkarbelaa-ctrl/osmaix-graph/actions/runs/40420406537
- All 44 tests passed in 0.39s; no skipped geometry tests.
- Run duration: 5m 44s; build job 5m 40s.
- One PBF snapshot: 2026-10-25T21:21:21Z (1792963281000).
- 19 complete governorates, including Halabja (osm-r3826029); no boundary errors.
- Full build with verify_determinism=true passed: the same snapshot was rebuilt
  with reversed way/relation input and all raw/compressed tile, manifest and
  report bytes compared before publication.
- Published release: https://github.com/martadhaelkarbelaa-ctrl/osmaix-graph/releases/tag/graph-iraq-20261025
- 20 gzip tiles plus manifest.json and report.json published; graph-latest was
  updated only after all dated assets were checked.
- Downloaded the dated and latest manifests independently: byte-identical.
- Downloaded Karbala tile locally: compressed SHA-256, raw SHA-256 and binary
  structure/CRC verified. Local private inspection completed; personal inputs
  and findings are deliberately absent from this repository.
- Verification artifact: iraq-graph-verification-40420406537, ID 12696398641,
  535,721 bytes, SHA-256 ddb40657fd1b7d88c3d0bdb0256097e06037e70362484efa22aa54e833e2f59c.

## Actual map acceptance measurements

- Backbone CAR weak component ratio: 0.9958877600 (required >=0.98).
- Backbone: 132,203 nodes, 149,137 edges, 16 directed ALT landmarks.
- Full backbone size with tertiary: 60,783,523 bytes; without: 33,279,070. Tertiary excluded because it exceeds 60,000,000 bytes; detailed governorate tiles retain it.
- Total storage, including overlap duplicates: 201,498,796 raw bytes; 88,330,455 gzip bytes.
- All 19 governorates exceed the required 0.90 CAR weak component ratio.
- Every individual release asset is below 2GB.
- Compression is gzip -9 for Android java.util.zip compatibility without an added dependency.

| Tile | Raw bytes | Gzip bytes | Largest CAR weak component |
|---|---:|---:|---:|
| backbone | 33,279,070 | 8,429,561 | 99.588776% |
| gov-iq-an | 8,628,456 | 3,961,444 | 99.544232% |
| gov-iq-ar | 18,595,438 | 9,318,654 | 99.016022% |
| gov-iq-ba | 10,285,548 | 4,530,489 | 98.577303% |
| gov-iq-bb | 5,606,924 | 2,531,445 | 99.881404% |
| gov-iq-bg | 19,528,217 | 8,405,041 | 99.718985% |
| gov-iq-da | 9,318,280 | 4,863,329 | 98.703168% |
| gov-iq-di | 10,721,462 | 5,076,991 | 99.331062% |
| gov-iq-dq | 4,884,687 | 2,244,147 | 99.946425% |
| gov-iq-ka | 5,293,360 | 2,337,120 | 99.689117% |
| gov-iq-ki | 7,954,461 | 3,833,301 | 99.688127% |
| gov-iq-ma | 3,150,399 | 1,340,083 | 99.236009% |
| gov-iq-mu | 2,608,644 | 1,172,211 | 99.553189% |
| gov-iq-na | 5,335,564 | 2,258,613 | 99.416995% |
| gov-iq-ni | 21,863,432 | 10,626,307 | 96.336660% |
| gov-iq-qa | 2,776,171 | 1,198,553 | 99.626205% |
| gov-iq-sd | 6,948,130 | 3,319,675 | 99.364884% |
| gov-iq-su | 19,519,339 | 10,416,631 | 99.379605% |
| gov-iq-wa | 3,747,292 | 1,665,236 | 99.801151% |
| gov-osm-r3826029 | 1,453,922 | 801,624 | 98.664541% |

## Previous failed runs and resolution

Runs 40419489184 and 40419993981 correctly failed on relation 21118515,
"حدود حي الامين": admin_level=4 with only a subarea relation and label node,
no outer boundary ways. The approved exact exception unblocked the new run.
No general rule for ignoring invalid boundaries was introduced.

## Application status / not yet verified

- The private app update/070 branch already contains earlier v1/Karbala stages
  2–4 at 5c76e8ea13a067e8b574ded7c72d7aceda769bff; stage-4 run 40417996096 passed.
- Iraq v2 TileManager, unified routing and later app stages are still pending.
- No Android APK was built for this Iraq change. No application ID, signing key,
  versionCode, routing default or user database was changed by the graph work.
- No physical-road accessibility, phone performance or field-test claim is made.

## Format / routing limitations to preserve

Backbone ALT alone is not admissible when detailed or personal shortcuts are
searchable. The unified router must use a valid geometric bound or recompute a
relaxed unified bound; do not blindly max backbone ALT with the geometric bound.
Directed differences of independently floored seconds subtract one second and
exclude INF. v1 reading remains covered by tests.

Binary bbox retains the national grid frame. Manifest polygonGeometry preserves
holes and islands and must be used for governorate coverage. Via-way and
conditional restrictions are counted but not applied. Per-tile component and
restriction details are in the published report.json.
