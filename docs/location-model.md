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

## Cross-dataset association

The point of Slice 5: an address *anywhere* in Chicago drives the correct query
to every parking dataset.

| dataset | keyed by |
|---|---|
| residential permit zones `qiag-khha` | street name + direction + **exact `address_number`** + parity |
| street sweeping `2r7q-emq3` | point-in-polygon → ward + section + schedule |
| temporary closures `rzy5-8tax` | street name + direction + address-range overlap + date |
| snow routes `i6k4-giaj` | street-name match against the resolved segment |
