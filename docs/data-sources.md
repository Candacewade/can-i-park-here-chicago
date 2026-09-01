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

## Researched, not yet integrated

| Purpose | Dataset | ID | Notes |
|---|---|---|---|
| Street closure / public-way permits | Transportation - Permits (Public Way Use / Closures) | `rzy5-8tax` | Point + street-range geometry, `applicationstartdate`/`applicationenddate`, `streetclosure` type. **Next MCP tool after Slice 1.** Original repo stub targeted this dataset. |
| Chicago municipal boundary | City Boundary | `qqq8-j68g` | Single multipolygon; used to bound the generated registry. |
| Street centerlines | Transportation - Street Center Lines | `6imu-meau` | Segment geometry + address ranges + cross-street names; basis for the generated block registry (Slice 5). |
| Snow / winter overnight parking ban routes | Winter Overnight Parking Ban | *(TBD)* | 2 AM–7 AM ban Dec 1–Apr 1 on ~107 mi regardless of snow, plus 2-inch routes. Needs verification of a machine-readable source. |
| Parking meters / paid zones | *(TBD — CDOT / concessionaire)* | *(TBD)* | No clean authoritative open dataset confirmed yet; may remain UNSUPPORTED. |
| Temporary "no parking" (moving, film, events) | *(TBD)* | *(TBD)* | Often issued as paper permits; open-data coverage uncertain. |

If no reliable official dataset exists for a category, the corresponding MCP
tool returns `UNSUPPORTED` and the rule engine keeps the answer `UNKNOWN` — we do
not pretend to support it.
