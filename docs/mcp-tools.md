# MCP Tools

Server: `chicago-parking` — `backend/app/mcp/server.py`, stdio transport, spawned
by the agent as `python -m app.mcp.server`. Logic in `app/mcp/handlers.py`.

Since the 2026-09-01 revision the **core** restriction data (residential, street
cleaning, temporary closures, winter-ban calendar) is gathered by the
deterministic core *before* the agent runs and handed to it as context — there
are no agent tools for those. The MCP toolbox is now the agent's **investigation
+ re-evaluation** surface.

Rules for every tool: one job; canonical `location_id` (never a free-text
address); structured JSON; data-source failure ⇒ explicit status. No generic
HTTP / filesystem / shell. Every tool takes the request's `run_id`; investigation
tools store their output in `app.evidence_store` under it.

| Tool | Purpose | Key args | Stores |
|---|---|---|---|
| `get_location_context` | confirm the block (street, cross streets, side, lat/lon) | `location_id` | — |
| `get_weather_outlook` | NWS forecast for the block over the interval: snowfall amount + probability, precip | `run_id, location_id, start_time, end_time` | `weather` |
| `get_snow_route_status` | is this block on a City 2-inch snow route | `run_id, location_id` | `snow_route` |
| `get_nearby_events` | special-event permits near the block during the interval (congestion / crowd context) | `run_id, location_id, start_time, end_time` | `events` |
| `get_closure_detail` | every public-way permit on the block (all work types, incl. non-parking) for explaining an unusual result | `run_id, location_id, start_time, end_time` | `closure_detail` |
| `find_legal_parking_nearby` | deterministic: nearby registry blocks that evaluate to LEGAL / LEGAL_UNTIL for the same interval + permit, nearest first | `run_id, location_id, start_time, end_time, permit_zone` | — |
| `evaluate_parking_request` | re-run the deterministic pipeline: **core gather (always)** + the optional evidence stored for this run + completeness + engine. Returns the authoritative `ParkingDecision` (status, `move_by`, `*_display`, `urgent_alert`, reasons, `unknown_reasons`). | `run_id, location_id, start_time, end_time, permit_zone` | — |
| `list_supported_locations` | discover valid `location_id`s | — | — |

## `evaluate_parking_request` is authoritative and independent

It never re-fetches from the agent and never accepts evidence arguments. It
gathers the required categories itself every call and merges only the optional
evidence the investigation tools stored under this `run_id`. The orchestrator
also runs this same evaluation once more after the agent finishes — that
post-agent result is what the API returns, so a misbehaving agent cannot change
the verdict.

## Weather / snow

`get_weather_outlook` calls NWS `api.weather.gov` (free, keyless). It is a
*forecast* — it feeds the agent's risk narrative, and only changes the
`snow_route` verdict when it confirms ≥2″ accumulation overlapping the interval
on a block that `get_snow_route_status` says is a 2-inch route. NWS outage ⇒
`weather` evidence `UNAVAILABLE`; the agent reports snow risk as unverified.
