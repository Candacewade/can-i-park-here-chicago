# Rule Engine

`backend/app/rules/` — the only place a LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN
verdict is produced. Pure functions, no LLM, no hidden I/O in the evaluator
itself.

## Pipeline

```
ParkingRequest
   │
   ▼
gather_evidence(request)              # rules/gather.py
   │  independently calls every data client (residential, street cleaning,
   │  temporary closure). Does NOT use anything the agent relayed.
   ▼
ParkingEvidence  (each category: VERIFIED | UNAVAILABLE | UNSUPPORTED)
   │
   ├─► check_completeness(request, evidence)      # rules/completeness.py
   │      required categories today: residential, street_cleaning,
   │      temporary_closure. Any not-VERIFIED  ⇒ incomplete.
   │
   ▼
evaluate_parking(request, evidence)   # rules/engine.py
   ▼
ParkingDecision { status, move_by, reasons[], unknown_reasons[] }
```

## Verdict precedence

`NOT_LEGAL  >  UNKNOWN  >  LEGAL_UNTIL  >  LEGAL`

1. **NOT_LEGAL** — a *verified* restriction is active at the requested start
   time (permit mismatch on a posted residential zone; street cleaning or a
   closure in effect at start). Wins even if other evidence is incomplete: you
   still cannot park.
2. **UNKNOWN** — no verified blocker, but a safety-required category was
   `UNAVAILABLE` / `UNSUPPORTED` / not gathered. `unknown_reasons` lists which.
3. **LEGAL_UNTIL** — everything verified and clear now, but a verified
   restriction begins during the interval. `move_by` = earliest such start.
4. **LEGAL** — everything verified, nothing conflicts.

## Per-category logic

| Category | `allows` | `blocks` (→ NOT_LEGAL) | `limits` (→ LEGAL_UNTIL) |
|---|---|---|---|
| residential | no zone, buffer zone, or `permit_zone` matches | posted zone, no/other permit | — (no hours data) |
| street_cleaning | no window overlaps interval | window active at start | window starts during interval |
| temporary_closure | no parking-impact permit overlaps | closure active at start | closure starts during interval |

Residential note: the City dataset has no posted *hours*, so a zone mismatch is
treated as in effect for the whole interval — the safe direction (never a false
"legal").

## Completeness ≠ agent behavior

The agent chooses which evidence tools to call. `evaluate_parking_request`
(the MCP tool) re-gathers everything itself and runs the completeness check, so a
tool the agent skipped simply shows up as "not gathered" → the affected category
is unverified → `UNKNOWN`. The agent cannot get a false `LEGAL` by forgetting a
check.
