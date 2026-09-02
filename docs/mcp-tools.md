# MCP Tools

Server: `chicago-parking` — `backend/app/mcp/server.py`, stdio transport, spawned
by the agent as `python -m app.mcp.server`.

Design rules (all tools): one clear job; descriptive name + description; canonical
`location_id` input (never a free-text address); structured JSON output; every
data-source failure surfaced as an explicit status, never as "no restriction".
The server exposes **no** generic HTTP, filesystem, or code-execution capability.

Descriptions say what a tool answers and when it is *relevant* — they do not
script a call order. The agent chooses.

Every tool except `get_location_context` / `list_supported_locations` takes a
**`run_id`** (supplied in the request). The evidence tools persist their
authoritative normalized output in `app.evidence_store` under
`(run_id, category, block/interval args)`. `evaluate_parking_request` reads that
stored evidence — it never re-fetches and never accepts evidence from the agent.
A required evidence tool that was not run for this `run_id` = missing evidence =
`UNKNOWN`. Implementations live in `app/mcp/handlers.py`.

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
| Arguments | `run_id: str`, `location_id: str` |
| Stores | `residential` evidence keyed by `location_id` |
| Returns | `ResidentialZoneEvidence` — `{status, zone_required, is_buffer, matched_segment, provenance, notes}` |
| Source | City of Chicago **Permit Parking Zones** (`qiag-khha`) |
| Failure | Portal error ⇒ `UNAVAILABLE`; unknown id ⇒ `UNSUPPORTED`; no covering segment ⇒ `VERIFIED` + `zone_required: null`. |
| Relevant when | The block might be in a residential zone, or a `permit_zone` was supplied. |

## `get_street_cleaning_restrictions`

| | |
|---|---|
| Purpose | Street-cleaning windows overlapping the interval. |
| Arguments | `run_id: str`, `location_id: str`, `start_time`, `end_time` (ISO-8601 + offset) |
| Stores | `street_cleaning` evidence keyed by `location_id` + interval |
| Returns | `StreetCleaningEvidence` — `{status, ward, section, windows: [{date, start, end, description}], provenance, notes}` |
| Source | City of Chicago **Street Sweeping Schedule - 2026** (`u5ai-3efk`) |
| Failure | Portal error ⇒ `UNAVAILABLE`; no ward/section ⇒ `UNSUPPORTED`; no overlap ⇒ `VERIFIED` + empty `windows`. |
| Relevant when | The interval could reach a daytime hour on a day the block is swept (overnight, early-morning, multi-day). |

## `get_temporary_closures`

| | |
|---|---|
| Purpose | Temporary street-closure / public-way permits removing on-street parking. |
| Arguments | `run_id: str`, `location_id: str`, `start_time`, `end_time` |
| Stores | `temporary_closure` evidence keyed by `location_id` + interval |
| Returns | `TemporaryClosureEvidence` — `{status, closures: [{permit_number, closure_type, start, end, meter_posting_or_bagging, work_description, blocks_parking}], provenance, notes}` |
| Source | City of Chicago **Transportation Permits / Street Closures** (`rzy5-8tax`) |
| Failure | Portal error ⇒ `UNAVAILABLE`; no matching permit ⇒ `VERIFIED` + empty `closures`. |
| Relevant when | Ruling out a short-notice construction/work-zone/event closure the recurring schedules wouldn't show. |

## `evaluate_parking_request`

| | |
|---|---|
| Purpose | The official deterministic parking decision. |
| Arguments | `run_id: str`, `location_id: str`, `start_time`, `end_time`, `permit_zone: str | null` |
| Returns | `{run_id, decision: ParkingDecision, completeness: {complete, missing[]}, evidence: ParkingEvidence}` |
| Source | Reads the evidence the other tools stored under this `run_id` (no re-fetch, no agent-relayed evidence), then `app/rules/`. |
| Decision fields | `status`, `move_by`, `reasons[]`, `unknown_reasons[]`, and `start_time_display` / `end_time_display` / `move_by_display` (America/Chicago) |
| Failure | Invalid request ⇒ `{decision: {status: "UNKNOWN"}, error}`. |
| Why the agent needs it | It is the *only* way to get a verdict. A required evidence tool not run for this `run_id` ⇒ `UNKNOWN`. The agent explains the result; it cannot compute or override `status` / `move_by` or reformat the dates. |

## `list_supported_locations`

| | |
|---|---|
| Purpose | Enumerate valid `location_id`s (discovery/debugging). |
| Arguments | none |
| Returns | `{locations: [{location_id, summary}]}` |
