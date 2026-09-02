# Authoritative Data Sources

All data is free and comes from the **City of Chicago Open Data Portal**
(`data.cityofchicago.org`), a Socrata instance queried through the SODA API.
No API key is required (an optional app token raises rate limits). No paid data
vendor is used anywhere.

Geographic universe: the City of Chicago municipal boundary — conceptually the
area Google Maps outlines as "Chicago". Google Maps is a *visual reference only*;
the machine-readable implementation uses official City geography (see
[location-model.md](location-model.md)).

---

## In use (Vertical Slice 1)

### Permit Parking Zones — residential permit parking

| | |
|---|---|
| Dataset ID | `qiag-khha` |
| Endpoint | `https://data.cityofchicago.org/resource/qiag-khha.json` |
| Format | JSON (SODA) |
| Update frequency | Daily; larger installments after City Council meetings |
| Client | [`app/services/residential_zones.py`](../backend/app/services/residential_zones.py) |
| MCP tool | `get_residential_restrictions` |

Fields we use: `street_name`, `street_direction`, `street_type`,
`address_range_low`, `address_range_high`, `odd_even` (`O`/`E`/blank = both
parities), `zone`, `buffer` (`Y` = residents may buy zone products but no signs
are posted), `status` (we filter to `ACTIVE`).

How we use it: given a block's bare street name, direction, representative
address, and parity, we find the covering ACTIVE segment and read the required
`zone`. No matching segment ⇒ the block is **not** in a residential zone
(a verified "no restriction", distinct from a data failure).

Known limitations: matching is by address range + parity, not geometry. Blocks
that straddle a zone boundary could match more than one segment; we prefer a
posted (non-buffer) segment.

### Street Sweeping Schedule - 2026 — street cleaning

| | |
|---|---|
| Dataset ID | `u5ai-3efk` |
| Endpoint | `https://data.cityofchicago.org/resource/u5ai-3efk.json` |
| Format | JSON (SODA) |
| Update frequency | Annual schedule; occasional revisions |
| Client | [`app/services/street_cleaning.py`](../backend/app/services/street_cleaning.py) |
| MCP tool | `get_street_cleaning_restrictions` |

Fields we use: `ward`, `section`, `month_name` / `month_number`, `dates`
(comma-separated day-of-month numbers, e.g. `"8,9"`).

How we use it: a block carries a sweeping `ward` + `section`; we pull that
section's schedule and emit a cleaning **window** for every scheduled date that
overlaps the requested interval.

Known limitations:
- **No time-of-day in the data.** Chicago posts sweeping as roughly 9 AM–3 PM;
  we use `09:00–15:00` America/Chicago as a documented default.
- The block → `ward`/`section` mapping is a geometry lookup we have not built
  yet. Development fixtures carry a hand-assigned section (Slice 5 automates it
  from the sweeping-section polygons).
- Schedule covers roughly April–November; outside that, "no rows" is reported as
  such, not as "no restriction forever".

---

### Transportation Permits / Street Closures — temporary closures

| | |
|---|---|
| Dataset ID | `rzy5-8tax` |
| Endpoint | `https://data.cityofchicago.org/resource/rzy5-8tax.json` |
| Format | JSON (SODA) |
| Update frequency | Continuous (permit lifecycle) |
| Client | [`app/services/street_closures.py`](../backend/app/services/street_closures.py) |
| MCP tool | `get_temporary_closures` |

Fields we use: `streetname`, `direction`, `streetnumberfrom`/`streetnumberto`,
`applicationstartdate`/`applicationenddate`, `applicationstatus` (`Open`/`Closed`),
`currentmilestone` (skip `Cancelled`), `streetclosure` (`Full`/`Curblane`/`Partial`),
`parkingmeterpostingorbagging` (`Y`).

How we use it: match permits by street + direction + address-range overlap +
date overlap with the interval; keep only `Open`, non-cancelled permits whose
closure removes the curb lane (`Full`/`Curblane`, or a meter-posting flag).

Known limitations: permits are day-granular (no hours); `Partial` closures
without a meter flag are treated as no parking impact; the dataset carries
occasional garbage dates (year 2105+) which we reject.

---

### Snow Route Parking Restrictions — 2-inch snow routes

| | |
|---|---|
| Dataset ID | `i6k4-giaj` |
| Endpoint | `https://data.cityofchicago.org/resource/i6k4-giaj.json` |
| Format | JSON (SODA); `the_geom` MultiLineString + `on_street` / `from_stree` / `to_street` |
| Client | `app/services/snow_routes.py` |
| MCP tool | `get_snow_route_status` |

144 arterial stretches where on-street parking is banned once **2+ inches** of
snow has accumulated. All rows are `restrict_t = "2 INCH"`. We match a block by
`on_street` (normalized street name + direction); the from/to granularity is
coarser than our blocks so a street-name match flags the block.

How the rule engine uses it: a bare route match is **advisory** (the ban only
bites with snow). It becomes a `blocks` / `limits` verdict only when the agent's
weather evidence (below) confirms ≥2″ accumulation overlapping the interval.

Known limitation: the separate **Dec 1 – Apr 1, 2–7 AM overnight ban** (~107 mi,
regardless of snow) applies to a *different, larger* arterial list for which we
have not confirmed a clean machine-readable source. `gather.py` applies the
**calendar** deterministically (interval in that window ⇒ `snow_route` becomes a
required category) but cannot yet assert the ban for a specific block. Tracked
for Slice 5.

### National Weather Service — snow forecast / observations

| | |
|---|---|
| Source | `https://api.weather.gov` (US NWS) — free, **no API key**, requires a `User-Agent` |
| Client | `app/services/weather.py` |
| Used by | the agent's investigation wing (not the deterministic core) |

Points → gridpoint forecast for the block's lat/lon; we read snowfall amount and
probability over the requested interval. This is a **forecast**, so it feeds the
agent's risk narrative and (only when it confirms ≥2″ on a 2-inch route) the
snow_route verdict. NWS outages ⇒ the agent reports the snow risk as unverified.

### Special events

Event permits with real parking impact (Block Party, Festival, Athletic, Parade,
Filming, …) are **already in the deterministic core** via the transportation-
permits dataset `rzy5-8tax` — those rows carry a `Full` / `Curblane` closure and
match like any other closure. The agent's "nearby event" role is *contextual*
(congestion, crowds, "the festival is that weekend"), drawing on the same
dataset or **Special Events Permits** (`dm95-f8w5`), and never changes legality.

---

## Researched, not yet integrated

| Purpose | Dataset | ID | Notes |
|---|---|---|---|
| Chicago municipal boundary | City Boundary | `qqq8-j68g` | Single multipolygon; used to bound the generated registry. |
| Street centerlines | Transportation - Street Center Lines | `6imu-meau` | Segment geometry + address ranges + cross-street names; basis for the generated block registry (Slice 5). |
| Winter overnight parking ban route list | *(map only so far: `nnn9-yqby`, `2cwz-8e8x`)* | — | The Dec 1–Apr 1 2–7 AM ban arterials. Need a tabular/geometry source. |
| Parking meters / paid zones | *(TBD — CDOT / concessionaire)* | *(TBD)* | No clean authoritative open dataset confirmed yet; may remain UNSUPPORTED. |

If no reliable official dataset exists for a category, the corresponding MCP
tool returns `UNSUPPORTED` and the rule engine keeps the answer `UNKNOWN` — we do
not pretend to support it.
