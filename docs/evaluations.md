# Agent Evaluations

`backend/evals/` — a small suite that runs the **real** agent against scenarios
with **pinned City data**, so the run is reproducible while the agent's
*behaviour* (tool selection, the verdict it lands on, what its explanation
says) is what's under test.

```bash
cd backend
python -m evals            # human report; exit 1 if any scenario fails
python -m evals --json     # machine-readable
```

It is **not** in CI — it spends Claude subscription usage. `pytest` only runs the
fast structural checks (`tests/unit/test_evals_structure.py`): scenarios parse,
tools are real, fixtures are well-shaped.

## How a scenario runs

```
Scenario           location_id + interval + permit + canned City data (+ weather)
  → write fixtures to a temp file; set EVAL_FIXTURES (forwarded to the MCP subprocess)
  → app.testing.fixtures.install_fixture_data  patches SocrataClient.get_rows,
    census_geocode, get_weather_outlook  (this process AND the MCP subprocess)
  → run_parking_agent(request, require_agent=True)     -- the real LLM call
  → score:
      decision status == expected
      move_by_display contains ...              (LEGAL_UNTIL scenarios)
      required tools were called / forbidden tools were not
      explanation contains the expected facts
      explanation contains NO loose reassurance ("probably fine", ...)
```

`app/testing/fixtures.py` and the `if os.environ.get("EVAL_FIXTURES")` guard in
`app/mcp/server.py` are the only eval hooks in the app code — dead on a normal
run.

## Scenarios (`evals/scenarios.py`)

| id | pins | asserts |
|---|---|---|
| `legal_clear` | nothing scheduled | LEGAL; no loose reassurance |
| `legal_until_street_cleaning` | sweeping 9 AM | LEGAL_UNTIL; `move_by` 9:00 AM; explanation says it |
| `not_legal_permit_offers_alternative` | zone 143, no permit | NOT_LEGAL; agent called `find_legal_parking_nearby` |
| `unknown_when_core_source_fails` | sweeping source 503 | UNKNOWN; explanation says "could not verify"; never "you can park" |
| `winter_snow_route_active` | winter, 2-inch route, 3.2″ forecast | agent called `get_weather_outlook`; NOT_LEGAL |

## Metrics (`evals/runner.py:metrics`)

`decision_accuracy`, `avg_tool_calls`, `reassurance_violations`, plus per-check
pass/fail. Start simple — JSON + a local report, `$0`.

## Debugging a failure — which layer broke?

| symptom | likely layer |
|---|---|
| right tools, wrong explanation | prompt / model |
| wrong tool chosen | tool *description* |
| tool returns garbage | tool code / a bad fixture |
| verdict wrong but evidence right | rule engine |
| evidence wrong | data client / schema / fixture shape |
