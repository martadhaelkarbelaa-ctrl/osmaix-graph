# OSMXG1 version 1 — explicit wire contract

All integers are little endian; coordinates are signed degrees × 10^7.
The binary layout follows the approved 0.7.0 specification. Edge records are
38 bytes (`<IIIHIBBHIIq`); turn records are 13 bytes (`<IIIB`). No native alignment.
Geometry contains both endpoints. An edge row stores geometry in OSM drawing
order. ONEWAY_BACK reverses traversal, not the stored geometry. Both oneway bits
clear means bidirectional; both set is invalid. CAR is the driving permission.

Flags: CAR=1, WALK=2, PENALTY=4, ACCESS_PRIVATE=8, DESTINATION_ONLY=16,
ONEWAY_FWD=32, ONEWAY_BACK=64, ROUNDABOUT=128, TRACK=256, LINK=512.
ACCESS_NO=1024 records an effective explicit OSM access prohibition. It must
coexist with ACCESS_PRIVATE, never CAR. Unlike private/unknown access, it must
NEVER be cleared by automatic driving evidence. This bit was allocated before
the first regional release; record width and format version remain unchanged.
Class IDs 0–22 follow `CLASSES` in graph_builder.py. Class 23 is service
parking_aisle/driveway, added to preserve its ×2 cost without changing the record
layout. Service class 14 costs ×1.5; track class 15 costs ×3. Speeds are km/h.
WALK edges explicitly granted CAR default to 15 km/h plus PENALTY; an explicit
maxspeed still takes precedence. Personal WALK car overrides without a chosen
speed must follow the same rule when the overlay stage is implemented.
Readers must reject unknown class/flag values and unsupported format versions.

Turn type 0 means forbidden. `fromEdge,viaNode,toEdge` identifies the direction
by arrival at/departure from viaNode. An only_* relation is expanded into
forbidden outgoing CAR edges. no_u_turn on one way prohibits reversal on the
same edge, not continuation on the adjacent edge with the same OSM way ID.
Unsupported via-way and conditional relations are counted in report.json;
they are NOT claimed to be enforced. This is a documented coverage limitation.

Grid: local equirectangular coordinates with Earth radius 6371008.8 m and
reference latitude `(bbox.minLat+bbox.maxLat)/2`. Origin `(minLon,minLat)`.
`x=floor(R*rad(lon-minLon)*cos(referenceLat)/250)`,
`y=floor(R*rad(lat-minLat)/250)`. Key packs x in the high signed 32 bits and y in
the low 32 bits; the combined key is stored as signed i64 and sorted as such.
Each cell contains sorted unique edge row IDs. All cells touched by the shape
are covered, including both sides when the line lies on a grid boundary.
Projection uses the E7-quantized header coordinates and geometry.

The footer is IEEE CRC32 of every preceding byte. SHA-256 in manifest.json
covers the entire file including CRC. Readers must check SHA, CRC, lengths,
counts, references, geometry endpoints, UTF-8, version and metadata before use.
Neither CRC nor a downloaded hash is a signature: updates require HTTPS from
the project's fixed trusted release location.

Determinism: sort by OSM way IDs, node IDs, names, restrictions and cell IDs.
sourceTimestamp comes from the source snapshot. buildTimestamp defaults to the
same logical build epoch (not the current clock); optional --build-timestamp
is an explicit reproducible input. Same input/options yields identical bytes.

Safety refinements approved in conversation:
- Generic access=yes on a footway does not prove car access; an explicit
  motorcar/motor_vehicle/vehicle grant is required.
- A recorded drive does not automatically override a legal one-way or turn ban.
- No guessed straight connector through buildings; unresolved access stays
  unresolved until verified.
- Local constraint rejection cannot be bypassed by ORS fallback.
- Enable the new engine by default only after all acceptance stages, inside
  the ORIGINAL applicationId and with the ORIGINAL signing key.
