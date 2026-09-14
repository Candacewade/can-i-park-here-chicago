# Location Model

A `location_id` is the single canonical handle for *where* a car is parked.
Everything downstream — the data services, rule engine, MCP tools, the agent, the
monitor — takes a `location_id` (or the `ChicagoParkingLocation` it resolves to)
and nothing else about location.

## `ChicagoParkingLocation`

`app/locations/registry.py`. One canonical parking segment: a street, a block,
and a side.

| field | meaning |
|---|---|
| `location_id` | stable id — `<street-slug>-<block-low>-<side>`, e.g. `n-clark-st-2400-west` |
| `street_name` | display name incl. direction, `N Clark St` |
| `address_number` | the exact house number resolved (Slice 5); `None` for legacy fixtures |
| `zip_code` | `60614` |
| `from_cross_street` / `to_cross_street` | the block's endpoints (from centerline topology) |
| `side` | `north` / `south` / `east` / `west` — always concrete (user-confirmed if ambiguous) |
| `address_parity` | `odd` / `even` / `any` — from `address_number` |
| `address_range_low` / `_high` | the matched segment's address range on this side |
| `street_sweeping_ward` / `_section` | from a point-in-polygon of the sweeping-zones dataset |
| `neighborhood` | Chicago community area — **display only, never rule input** |
| `latitude` / `longitude` | the resolved point |

## Resolution — `app/locations/resolve.py`

```
resolve_address(number, street, zip) -> ResolvedLocation
```

1. **Geocode** — US Census Bureau (`geocoding.geo.census.gov/geocoder/locations/
   onelineaddress`, free, no key). Returns the matched address, coordinates,
   normalized street parts (`streetName`, `preDirection`, `suffixType`), the
   block's address range on the matched side (`fromAddress`/`toAddress`), and the
   TIGER `side` (`L`/`R`).
2. **In-Chicago gate** — `qqq8-j68g` `intersects(POINT(lon lat))`. Outside ⇒
   `in_chicago=false`, resolution stops (the UX says "not in supported Chicago
   coverage").
3. **Canonical segment** — `pr57-gg9e` (Chicago Street Center Lines) where
   `street_nam` + `pre_dir` match and `number` falls in `l_f_add..l_t_add` or
   `r_f_add..r_t_add`. Gives `the_geom`, `fnode_id`/`tnode_id`, and both ranges.
4. **Side** — see below.
5. **Cross streets** — `pr57-gg9e` where `fnode_id`/`tnode_id` equals either
   endpoint node and `street_nam` differs. The two distinct names are the block's
   `from`/`to` cross streets.
6. **Sweeping ward/section** — `2r7q-emq3` (Street Sweeping Zones 2026)
   `intersects(POINT(...))` → `ward`, `section`, and that zone's month-by-month
   schedule.
7. **Neighborhood** — `igwz-8jzy` (Community Areas) `intersects(...)`.
8. **Build** the `ChicagoParkingLocation` + `location_id`; persist to
   `blocks.json`.

**Census down / no match** ⇒ fall back to step 3 by street + number only;
segment centroid becomes the point for steps 6–7; side uses the parity
convention with lowered confidence.

## Side of the street

The compass side is derived, then confirmed:

- **Geometry:** the Census address point is offset to the correct physical side
  of the street. The signed cross-product of `(segment end − segment start)` with
  `(point − segment start)` gives left/right of travel; the segment bearing
  (dominant of Δlat vs Δlon) gives orientation. left/right + orientation →
  `north|south|east|west`.
- **Convention cross-check:** Chicago's 1909 grid puts **even** numbers on the
  **south and west** sides, **odd** on the **north and east**. Agreement with the
  geometry ⇒ `confidence: high`.
- **Disagreement, or a short/curved segment, or the Census fallback** ⇒
  `confidence: low`, and `side_options` carries both candidates.

`POST /api/locations/resolve` always returns `side.suggested` + `side.options` +
`side.confidence`. **The frontend always shows a side confirmation** (pre-checked
to the suggestion). The rule engine only ever sees a concrete, confirmed side; a
watch stores the confirmed side. We never silently guess.

**Each `side_options` entry also carries `required_permit_zone` /
`permit_zone_is_buffer`** (`app/api/main.py:_side_candidate`) — a real,
block-and-side-exact lookup against the same `qiag-khha` dataset the rule
engine itself uses (`get_residential_zone_evidence`), not a neighborhood-level
guess. The frontend (`BlockConfirm.tsx`) uses it to prefill the permit-zone
field when empty, and to flag a mismatch if the user's entered/remembered zone
differs from what this specific block actually requires. A failed lookup just
omits the field (`side_options[].required_permit_zone: null`) — it never
fabricates a zone number.

## The registry

`get_location(location_id)`:

1. in-process cache
2. `blocks.json` — the self-populating registry. It is **user data** (which
   blocks people looked up), so it lives in the **private data repo**
   (`app/json_store.py:data_store`), or a git-ignored `backend/.data/` file
   locally. Never in the public repo.
3. on a miss: parse the `location_id` → synthesize a representative address →
   run `resolve_address` → write the result to the private `blocks.json`
4. `fixtures.json` — a handful of hand-written blocks kept for tests (non-user)

So the "citywide registry" is not a giant pre-generated file — it is a private
cache that fills in as real addresses are looked up, backed by live official
geometry.

## Reverse geocoding — `app/locations/reverse.py`

"Use my current location" (`POST /api/locations/reverse`, browser
`navigator.geolocation`) turns coordinates into a plausible address using
**only** the Street Center Lines dataset already in use above — no
third-party geocoding service, no new external dependency, $0:

```
(lat, lon)
  → within_circle() spatial query, pr57-gg9e, 150m radius
    (the only place in the codebase that queries this dataset by proximity
    rather than by street name -- everywhere else is name+number driven)
  → nearest_point_on_segment() (app/geo.py) picks the closest candidate,
    projecting the point onto each segment to get a distance + how far
    along it (t ∈ [0,1])
  → signed_side() (already used for forward resolution) decides left/right
    of travel, choosing the L or R address-range field pair
  → estimated house number = lo + t × (hi - lo) on that range
  → handed to the EXISTING resolve_address(estimated_number, street, "")
    -- re-verified from scratch (city boundary, side, cross streets,
    sweeping zone) exactly as a typed address would be
```

This is deliberately an *estimate feeding a real re-verification*, not an
authoritative answer on its own — `reverse_geocode()` never constructs a
`ChicagoParkingLocation` directly. The frontend still shows the normal
block/side confirmation step before anything runs; a wrong house-number
guess just means confirming a different side/number, same as a typo in the
typed-address flow would. No nearby segment (outside Chicago, or too far from
any mapped street) → `None` → the endpoint reports it the same way an
unmatched typed address is reported, never a raw error.

## Map picker — `frontend/src/components/MapPicker.tsx`

"Pick on a map" (next to "Use my current location") is a fully self-hosted,
$0 interactive map with a live "you are here" dot. Tapping it hands the
tapped `(lat, lon)` to the exact same `reverse_geocode()` flow above — the
map is only ever an *input method* for coordinates, never a new data path.

**Stack** (all free, open source, no account/key):
[MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) (a pre-paywall
Mapbox GL JS fork) + [pmtiles](https://github.com/protomaps/pmtiles) (reads a
single static tile file over HTTP range requests — no tile server) +
[`@protomaps/basemaps`](https://github.com/protomaps/basemaps) (generates the
MapLibre style/layers for the Protomaps basemap vector schema). The blue dot
is MapLibre's built-in `GeolocateControl`, backed by the same
`navigator.geolocation` the "Use my current location" button already uses —
no new browser API.

**Map tiles: `frontend/public/chicago.pmtiles` (~64MB, committed to the
repo).** This is a Chicago-only extract of
[Protomaps' daily OSM-derived basemap build](https://docs.protomaps.com/basemaps/downloads),
built once with their free `pmtiles` CLI (a small Go binary,
[releases](https://github.com/protomaps/go-pmtiles/releases)) — it pulls
*only* the bytes for the requested bounding box via HTTP range requests
against the remote build, not the ~120GB planet file:

```
pmtiles extract https://build.protomaps.com/<YYYYMMDD>.pmtiles chicago.pmtiles \
  --bbox=-87.955,41.63,-87.5,42.04
```

(`<YYYYMMDD>` = a recent date; Protomaps keeps roughly the last few days of
daily builds live at that URL — check `curl -I` on a candidate date first.)
The bbox comfortably covers the city; z0–15 (the source's full range) came to
64MB. **This step needs to be re-run only if the data goes noticeably stale
or the covered area needs to change** — it is not part of any build/deploy
process, and re-running it grows the git history by another ~64MB each time,
so don't do it casually.

Once extracted, the file is served as a plain static asset (same as any
other file in `frontend/public/`) — Vercel's existing free hosting, no new
infrastructure. `MapPicker.tsx` references it via
`pmtiles://<origin>/chicago.pmtiles`.

**Fonts and icons** (`glyphs`/`sprite` in the MapLibre style) are referenced
directly from Protomaps' own free, keyless, GitHub-Pages-hosted companion
assets (`protomaps.github.io/basemaps-assets/...`) rather than self-hosted —
static file serving with no rate limit, not a live queried service, so this
was judged consistent with "no new external dependency" without needing a
separate sign-off; unlike the tile data it's a handful of KB per session, not
a 64MB asset worth bundling into this repo.

**Attribution:** the vector source's `attribution` field carries "©
Protomaps © OpenStreetMap" (ODbL requires the OpenStreetMap credit); MapLibre
renders it automatically via its attribution control.

**Performance:** `MapPicker` is loaded via `React.lazy()` — MapLibre GL is
~300KB gzipped, so it's fetched only when someone actually opens the map, not
on every page load (`AddressForm.tsx`'s bundle stays ~72KB gzipped either
way).

## Cross-dataset association

The point of Slice 5: an address *anywhere* in Chicago drives the correct query
to every parking dataset.

| dataset | keyed by |
|---|---|
| residential permit zones `qiag-khha` | street name + direction + **exact `address_number`** + parity |
| street sweeping `2r7q-emq3` | point-in-polygon → ward + section + schedule |
| temporary closures `rzy5-8tax` | street name + direction + address-range overlap + date |
| snow routes `i6k4-giaj` | street-name match against the resolved segment |
