# Agent Evaluations

> **Status: designed, not yet built.** This is the next major piece of work after
> deployment (Master Build Plan §38–39). The tracing that evals build on already
> exists — every agent run captures tool calls, args, results, latency, and the
> deterministic decision (`AgentRunResult` / `format_trace`).

## Why evals matter here

The agent's job is now narrow (investigation + communication, never legality), so
the eval surface is narrow too. What we need to keep honest:

- the agent **investigates when it should** (winter → weather; NOT_LEGAL →
  alternatives) and **doesn't waste calls** when it shouldn't
- the agent **never states a verdict** the rule engine didn't produce, and never
  contradicts / softens `status`, `move_by`, or an urgent alert
- the agent **restates the `*_display` strings** rather than computing dates
- `UNAVAILABLE` / `UNSUPPORTED` is reported as unverified, never "you're fine"
- instruction-injection in any free text (there is little) can't move the verdict

## Scenario shape

```
INPUT              a ParkingRequest (fixture or resolved address) + a fixed clock
FIXTURE DATA       canned City-dataset responses (so the run is deterministic)
REQUIRED TOOLS     e.g. {get_weather_outlook}   -- must appear
OPTIONAL TOOLS     e.g. {get_nearby_events}
FORBIDDEN TOOLS    e.g. {}                       -- must NOT appear
EXPECTED STATUS    LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN
EXPECTED move_by   optional
EXPECTED FACTS     substrings that must be in the explanation
FORBIDDEN PHRASES  e.g. "probably fine", "you should be okay"
```

## Metrics (start simple — JSON + pytest, $0)

decision accuracy · required-tool recall · unnecessary-tool-call rate · average
tool calls · UNKNOWN-handling accuracy · hallucinated-rule rate · rule-engine
override attempts · explanation factual accuracy · latency.

## How it runs

`backend/evals/` — a separate suite, **not** in the fast CI (it spends Claude
subscription usage). Run manually / on a cadence. Each scenario mocks the City
data so only the agent's *behavior* is under test; the deterministic verdict is
computed the same way production does it.

## Debugging a failure — which layer broke?

| symptom | likely layer |
|---|---|
| right tools, wrong explanation | prompt / model |
| wrong tool chosen | tool *description* |
| tool returns garbage | tool code / City data |
| verdict wrong but evidence right | rule engine |
| evidence wrong | data client / schema |
