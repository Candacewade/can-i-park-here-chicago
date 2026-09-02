# Rule Engine

`backend/app/rules/` — pure functions, no LLM, no hidden I/O in the evaluator.
The **only** place a verdict, a move-by time, or a hard urgent-alert trigger is
produced. Since the 2026-09-01 revision this layer runs on every request with no
agent involvement.

## Pipeline

```
ParkingRequest
   │
   ▼
gather_evidence(request)               # rules/gather.py  — ALWAYS
   │  residential · street_cleaning · temporary_closure
   │  (+ snow_route when the interval is in the winter overnight-ban period)
   │  each data-source failure ⇒ EvidenceStatus.UNAVAILABLE (never "no restriction")
   ▼
ParkingEvidence
   │
   │◄── agent investigation wing may add: snow_route (off-season), weather
   │    outlook, event impact, closure detail — into the per-run evidence store,
   │    then merged here and re-evaluated
   ▼
check_completeness(request, evidence)   # rules/completeness.py
   │  required_categories(request):
   │    always  → residential, street_cleaning, temporary_closure
   │    winter  → + snow_route   (interval overlaps Dec 1 – Apr 1)
   │  any required category None / not VERIFIED ⇒ incomplete
   ▼
evaluate_parking(request, evidence)     # rules/engine.py
   ▼
ParkingDecision {
   status, move_by, reasons[], unknown_reasons[],
   start_time_display, end_time_display, move_by_display,   # America/Chicago
   urgent_alert: bool, urgent_reason: str | None            # hard trigger
}
```

`gather.py` is the **primary** path (Slice 2 called it a "non-agent baseline";
that framing is gone). The agent path and any direct/eval path both go through
it.

## Verdict precedence

`NOT_LEGAL  >  UNKNOWN  >  LEGAL_UNTIL  >  LEGAL`

1. **NOT_LEGAL** — a *verified* restriction is active at the requested start
   time. Wins even under incomplete evidence.
2. **UNKNOWN** — no verified blocker, but a required category is
   `UNAVAILABLE` / `UNSUPPORTED` / not gathered.
3. **LEGAL_UNTIL** — clear now, a verified restriction begins during the
   interval. `move_by` = earliest such start.
4. **LEGAL** — everything verified, nothing conflicts.

## Hard urgent-alert trigger

Deterministic, computed in `engine.py` alongside the verdict:

> `urgent_alert = True` when the decision is `NOT_LEGAL`, or `LEGAL_UNTIL` with
> `move_by` within the **urgent window** (default: the next `URGENT_WINDOW_HOURS`
> = 12h from "now", or from the interval start for a future request).

When `urgent_alert` is set, the Slice 4 monitor **must** send an alert. Claude
composes and prioritizes the message; Claude cannot suppress the trigger.

## Per-category logic

| Category | `allows` | `blocks` → NOT_LEGAL | `limits` → LEGAL_UNTIL |
|---|---|---|---|
| residential | no zone / buffer / `permit_zone` matches | posted zone, no/other permit | — (no hours in data) |
| street_cleaning | no window overlaps | window active at start | window starts during interval |
| temporary_closure | no parking-impact permit overlaps | closure active at start | closure starts during interval |
| snow_route | block not on a 2-inch route | on a 2-inch route **and** agent weather evidence confirms ≥2″ accumulation in the interval | on a 2-inch route, ≥2″ forecast later in the interval |

Snow note: the 2-inch ban only bites once snow falls, so a bare route match is
advisory; it becomes `blocks` / `limits` only with verified weather evidence
from the agent. The separate Dec 1–Apr 1 2–7 AM overnight ban applies to a
specific arterial list we do not yet have machine-readable — documented in
[data-sources.md](data-sources.md), tracked for Slice 5.

## `find_legal_parking_nearby(location_id)`   (rules/nearby.py)

Deterministic. Takes the requested block, walks nearby registry blocks (by
distance), runs the same core pipeline on each for the same interval + permit,
and returns those that come back `LEGAL` or `LEGAL_UNTIL`, nearest first. The
agent chooses when to call it and how to present the options; it does not judge
the individual results.

## Completeness ≠ agent behavior

The required gather is unconditional, so the required categories are always
present unless a data source failed. The agent can only *add* optional evidence;
a required category it forgot cannot exist because the agent never owned it.
