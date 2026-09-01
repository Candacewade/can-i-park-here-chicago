# MCP Tools

Server: `chicago-parking` — `backend/app/mcp/server.py`, stdio transport, spawned
by the agent as `python -m app.mcp.server`.

Design rules (all tools): one clear job; descriptive name + description; canonical
`location_id` input (never a free-text address); structured JSON output; every
data-source failure surfaced as an explicit status, never as "no restriction".
The server exposes **no** generic HTTP, filesystem, or code-execution capability.

Descriptions say what a tool answers and when it is *relevant* — they do not
script a call order. The agent chooses. `evaluate_parking_request` re-gathers
evidence itself and runs a deterministic completeness check, so a skipped tool
cannot become a false "you can park".

---

## `get_location_context`

| | |
|---|---|
| Purpose | Resolve a `location_id` to its Chicago block and confirm it is supported. |
| Arguments | `location_id: str` |
| Returns | `{found, location: {...}, summary}` or `{found: false, error}` |
| Source | Location registry (`app/locations/`) |
| Failure | Unknown id ⇒ `found: false` (outside supported Chicago coverage). |
| Why the agent needs it | To verify it is reasoning about the right block. |

## `get_residential_restrictions`

| | |
|---|---|
| Purpose | Residential permit-parking status for the block + side. |
| Arguments | `location_id: str` |
| Returns | `ResidentialZoneEvidence` — `{status, zone_required, is_buffer, matched_segment, provenance, notes}` |
| Source | City of Chicago **Permit Parking Zones** (`qiag-khha`) |
| Failure | Portal error ⇒ `UNAVAILABLE`; unknown id ⇒ `UNSUPPORTED`; no covering segment ⇒ `VERIFIED` + `zone_required: null`. |
| Relevant when | The block might be in a residential zone, or a `permit_zone` was supplied. |

## `get_street_cleaning_restrictions`

| | |
|---|---|
| Purpose | Street-cleaning windows overlapping the interval. |
| Arguments | `location_id: str`, `start_time`, `end_time` (ISO-8601 + offset) |
| Returns | `StreetCleaningEvidence` — `{status, ward, section, windows: [{date, start, end, description}], provenance, notes}` |
| Source | City of Chicago **Street Sweeping Schedule - 2026** (`u5ai-3efk`) |
| Failure | Portal error ⇒ `UNAVAILABLE`; no ward/section ⇒ `UNSUPPORTED`; no overlap ⇒ `VERIFIED` + empty `windows`. |
| Relevant when | The interval could reach a daytime hour on a day the block is swept (overnight, early-morning, multi-day). |

## `get_temporary_closures`

| | |
|---|---|
| Purpose | Temporary street-closure / public-way permits removing on-street parking. |
| Arguments | `location_id: str`, `start_time`, `end_time` |
| Returns | `TemporaryClosureEvidence` — `{status, closures: [{permit_number, closure_type, start, end, meter_posting_or_bagging, work_description, blocks_parking}], provenance, notes}` |
| Source | City of Chicago **Transportation Permits / Street Closures** (`rzy5-8tax`) |
| Failure | Portal error ⇒ `UNAVAILABLE`; no matching permit ⇒ `VERIFIED` + empty `closures`. |
| Relevant when | Ruling out a short-notice construction/work-zone/event closure the recurring schedules wouldn't show. |

## `evaluate_parking_request`

| | |
|---|---|
| Purpose | The official deterministic parking decision. |
| Arguments | `location_id: str`, `start_time`, `end_time`, `permit_zone: str | null` |
| Returns | `{decision: ParkingDecision, completeness: {complete, missing[]}, evidence: ParkingEvidence}` |
| Source | Re-gathers **all** datasets itself (ignores agent-relayed evidence), then `app/rules/`. |
| Failure | Invalid request ⇒ `{status: "UNKNOWN", error}`. |
| Why the agent needs it | It is the *only* way to get a verdict. The agent cannot compute or override `status` / `move_by`; it calls this once it has gathered what the request needs, then explains the result. |

## `list_supported_locations`

| | |
|---|---|
| Purpose | Enumerate valid `location_id`s (discovery/debugging). |
| Arguments | none |
| Returns | `{locations: [{location_id, summary}]}` |
