# Rule Engine

`backend/app/rules/` — the only place a LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN
verdict is produced. Pure functions, no LLM, no hidden I/O in the evaluator
itself.

## Pipeline (agent path)

```
agent calls get_residential_restrictions(run_id, ...)      ─┐
agent calls get_street_cleaning_restrictions(run_id, ...)   │  each tool fetches +
agent calls get_temporary_closures(run_id, ...)            ─┘  normalizes, then
                                                               app.evidence_store.record(run_id, category, args, evidence)

agent calls evaluate_parking_request(run_id, location_id, start, end, permit_zone)
   │
   ▼
evidence_store.build_bundle(run_id, location_id, start, end)   # app/evidence_store.py
   │  returns a ParkingEvidence built ONLY from stored entries whose recorded
   │  args match this block + interval. Anything not gathered (or gathered for a
   │  different block/interval) is None.
   ▼
ParkingEvidence  (each category: VERIFIED | UNAVAILABLE | UNSUPPORTED | None)
   │
   ├─► check_completeness(request, evidence)      # rules/completeness.py
   │      required: residential, street_cleaning, temporary_closure.
   │      any None or not-VERIFIED  ⇒ incomplete.
   │
   ▼
evaluate_parking(request, evidence)   # rules/engine.py
   ▼
ParkingDecision { status, move_by, reasons[], unknown_reasons[],
                  start_time_display, end_time_display, move_by_display }
```

`start_time_display` / `end_time_display` / `move_by_display` are
`America/Chicago` strings ("Tuesday, September 9, 2026 at 9:00 AM") computed
here. The agent restates them verbatim and does no date/time math itself.

`rules/gather.py:gather_evidence()` is the **non-agent** equivalent (fetches all
categories in one call) — used by tests and future eval baselines, not on the
agent path.

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

The agent chooses which evidence tools to call, and those calls are what the
evaluator actually uses. But a tool the agent skipped simply has no entry in the
store → that category is `None` → completeness fails → `UNKNOWN`. The agent
cannot get a false `LEGAL` by forgetting a check, and it cannot hand-craft or
edit evidence — only the tools write to the store, and only with what they
fetched from the City.
