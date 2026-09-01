# MCP Tools

Server: `chicago-parking` — `backend/app/mcp/server.py`, stdio transport, spawned
by the agent as `python -m app.mcp.server`.

Design rules (all tools): one clear job; descriptive name + description; canonical
`location_id` input (never a free-text address); structured JSON output; every
data-source failure surfaced as an explicit status, never as "no restriction".
The server exposes **no** generic HTTP, filesystem, or code-execution capability.

---

## `get_location_context`

| | |
|---|---|
| Purpose | Resolve a `location_id` to its Chicago block and confirm it is supported. |
| Arguments | `location_id: str` |
| Returns | `{found, location: {street_name, from/to_cross_street, side, neighborhood, address range, street_sweeping_ward/section, lat/lon}, summary}` or `{found: false, error}` |
| Source | Location registry (`app/locations/`) |
| Failure | Unknown id ⇒ `found: false` (location outside supported Chicago coverage). |
| Why the agent needs it | To verify it is reasoning about the right block before spending calls on restriction lookups. |

## `get_residential_restrictions`

| | |
|---|---|
| Purpose | Residential permit-parking status for the block + side. |
| Arguments | `location_id: str` |
| Returns | `ResidentialZoneEvidence`: `{status, zone_required, is_buffer, matched_segment, provenance, notes}` |
| Source | City of Chicago **Permit Parking Zones** (`qiag-khha`) |
| Failure | Portal error/timeout/bad shape ⇒ `status: UNAVAILABLE`. Unknown id ⇒ `UNSUPPORTED`. No covering segment ⇒ `VERIFIED` with `zone_required: null`. |
| Why the agent needs it | To know whether a permit is required and which zone — decisive whenever a `permit_zone` is supplied. |

## `get_street_cleaning_restrictions`

| | |
|---|---|
| Purpose | Street-cleaning windows overlapping the requested interval. |
| Arguments | `location_id: str`, `start_time: str` (ISO-8601 + offset), `end_time: str` |
| Returns | `StreetCleaningEvidence`: `{status, ward, section, windows: [{date, start, end, description}], provenance, notes}` |
| Source | City of Chicago **Street Sweeping Schedule - 2026** (`u5ai-3efk`) |
| Failure | Portal error ⇒ `UNAVAILABLE`. No ward/section on the block ⇒ `UNSUPPORTED`. No overlapping date ⇒ `VERIFIED` with empty `windows`. |
| Why the agent needs it | Street cleaning is the most common Chicago ticket for overnight parking; always checked for overnight/multi-day intervals. |

## `list_supported_locations`

| | |
|---|---|
| Purpose | Enumerate valid `location_id`s (discovery/debugging). |
| Arguments | none |
| Returns | `{locations: [{location_id, summary}]}` |
| Why the agent needs it | Rarely — the `location_id` is normally supplied in the request. |
