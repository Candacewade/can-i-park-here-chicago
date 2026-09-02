# Agent Design

Since the 2026-09-01 revision the agent is **not** in the legality path. The
deterministic core (`app/rules/`) gathers required evidence, checks completeness,
and produces the `ParkingDecision` before the agent runs at all. The agent is
two optional wings around that result.

## What the agent controls

**Investigation wing** — decides whether the situation is worth extra digging,
and does it:

| Trigger the agent reasons about | Tool it reaches for |
|---|---|
| interval is in winter / snow is plausible | `get_snow_route_status`, `get_weather_outlook` (NWS) |
| a big venue / event area is near the block | `get_nearby_events` |
| a temporary-closure result looks odd or severe | `get_closure_detail` |
| the user asks where they could move instead | `find_legal_parking_nearby` |

New evidence is written to `app.evidence_store` under the run's `run_id`. If a
**deterministic** trigger promoted a category to required (e.g. the interval
overlaps Dec 1–Apr 1 ⇒ `snow_route` required) and the agent supplied it, the
pipeline re-evaluates.

**Communication wing** — prioritizes, judges urgency, and writes:
the grounded explanation, the daily monitoring email, alert copy, and
contextual recommendations ("street cleaning is also due two days later").

## What the agent does NOT control

- **Whether a safety check runs.** The core gather is unconditional.
- **Legality** — `status`, `move_by` — decided only by `evaluate_parking()`.
- **Whether a hard urgent alert fires.** If a verified restriction requires the
  car to move within the urgent window, deterministic code sets the flag. The
  agent decides how to prioritize and word it, not whether to send it.
- **Evidence content** — every evidence object is produced by a data client and
  stored by application code; the agent never assembles or edits evidence.
- **Dates / weekdays / time zones** — the decision carries
  `start_time_display`, `end_time_display`, `move_by_display` (America/Chicago).
  The agent restates them; it must not compute or convert a time.
- **Missing-data assumptions** — `UNAVAILABLE` / `UNSUPPORTED` / not-gathered
  stays unverified and never becomes "you can park".

## Runtime & auth

Claude Agent SDK (`claude-agent-sdk`), model `claude-sonnet-4-5`, authenticated
through the local Claude Code CLI (subscription, no `ANTHROPIC_API_KEY`). CLI
discovery: `app/config.py:resolve_claude_cli()`.

**The agent is optional.** `run_parking_agent(request)` runs the deterministic
core first and returns it unconditionally. If the CLI is missing it sets
`agent_available = False`, writes a deterministic-template explanation
(`_deterministic_explanation`), and returns — no raise. Only
`run_parking_agent(request, require_agent=True)` (the Slice 4 monitor) raises
`AgentAuthError` so the monitor can fall back to its own email template.

## Orchestration & lockdown

`app/agent/parking_agent.py`:

1. run the deterministic core → `ParkingDecision` + evidence + hard-alert flags
   (this is the answer; it is what `/api/parking/analyze` always returns)
2. if the Claude runtime is present: hand the decision to the agent as context,
   with a fresh `run_id`; the agent investigates (optional) and composes prose
3. else: deterministic-template explanation, empty trace
4. capture every tool call (name, args, result, latency, order) for the trace
5. **replay** the verdict-relevant evidence the agent gathered (weather, events,
   off-season snow) from the tool traces into *this* process's evidence store —
   the agent's tools ran in the MCP **subprocess** whose in-process store the
   parent does not share — then re-run the deterministic pipeline as the
   authoritative `result.decision`

`ClaudeAgentOptions`: `setting_sources=[]` (no repo `CLAUDE.md`), a `can_use_tool`
callback that allows **only** `mcp__chicago-parking__*`, `disallowed_tools` for
the built-ins, MCP server as a stdio subprocess.

## Instructions

Version-controlled in `app/agent/instructions.py` as `SYSTEM_PROMPT_V2`. The hard
constraints (no legality from memory, no invented rules, use the supplied
`location_id` and times, missing data ≠ permission, never state or change a
verdict, no date math) are load-bearing. Prompt experiments keep V2 as the
baseline.

## Concepts (for the learning goal)

- **Why this is still an agent**: it is given a goal (assess + communicate a
  parking situation) and a toolbox, and it decides *whether and what* to
  investigate and *how* to communicate — genuine judgment, just not over
  legality.
- **Deterministic vs. probabilistic boundary**: the required checks, the
  verdict, the move-by time, and the hard urgent-alert trigger are all pure
  Python. The agent's freedom lives strictly outside that boundary.
- **Why `run_id`**: the orchestrator mints it; every tool call carries it;
  optional evidence the agent gathers is stored under it and merged into the
  next evaluation. The agent's investigation is operationally real without the
  evidence passing through the model.
