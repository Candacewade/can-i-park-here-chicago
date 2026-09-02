# Agent Design

## What Claude controls

- **Tool selection** — which MCP tools to call for a given request.
- **Tool sequence** — the order (e.g. context first, then restriction lookups).
- **Tool arguments** — built from the canonical `ParkingRequest` fields.
- **Evidence organization** and the **plain-language explanation** of the final
  decision.

## What Claude does NOT control

- **Parking legality** — decided only by `evaluate_parking()`.
- **Evidence content** — each MCP evidence tool fetches and stores its own
  authoritative output in `app.evidence_store` under the run's `run_id`. The
  agent never assembles, edits, or relays evidence; `evaluate_parking_request`
  reads it straight from the store.
- **Rule interpretation** outside of what a tool result literally says.
- **Missing-data assumptions** — `UNAVAILABLE` / `UNSUPPORTED` / not-gathered
  stays unverified; it never becomes "you can park".
- **Overriding the evaluator** — the agent receives a finished `ParkingDecision`
  and may not change its `status` or `move_by`.
- **Dates and times** — the decision carries `start_time_display`,
  `end_time_display`, `move_by_display` (America/Chicago). The agent restates
  those strings; it must not compute a weekday or convert a time.

## Runtime & auth

Claude Agent SDK (`claude-agent-sdk`), model `claude-sonnet-4-5`. The SDK shells
out to the local **Claude Code CLI**, which carries the Claude Pro subscription
credentials — we do not set `ANTHROPIC_API_KEY`. CLI discovery:
`app/config.py:resolve_claude_cli()`.

## Tool lockdown

`app/agent/parking_agent.py` builds `ClaudeAgentOptions` with:

- `setting_sources=[]` — the agent does **not** inherit this repo's `CLAUDE.md`
  or settings.
- `can_use_tool` callback — allows **only** `mcp__chicago-parking__*`; everything
  else is denied.
- `disallowed_tools` — belt-and-braces block of `Bash`, `Edit`, `Write`, `Read`,
  `WebFetch`, `Task`, `ToolSearch`, etc.
- MCP server registered as a stdio subprocess (`python -m app.mcp.server`).

## Instructions

Version-controlled in `app/agent/instructions.py` as `SYSTEM_PROMPT_V1`. Wording
may be tuned; the hard rules (no legality from memory, no invented regulations,
use the supplied `location_id`, don't alter times, missing data ≠ permission,
never state a verdict) are load-bearing. Prompt experiments (Master Build Plan
sec. 40) keep V1 as the baseline.

## Tracing

Every run captures, per tool call: order, name, arguments, result, error flag,
latency. `format_trace()` renders it; `AgentRunResult.evidence` holds the
normalized evidence bundle passed to the rule engine.

## Concepts (for the learning goal)

- **Why this is an agent**: Claude is given a goal and a toolbox and decides the
  steps — which tools, what arguments, in what order — rather than following a
  fixed script.
- **How tool selection works**: Claude sees each tool's *name* and *description*
  (not its code). Strong descriptions that say *when* to use a tool drive good
  selection; that is why our descriptions include trigger conditions.
- **How arguments travel**: Claude emits a `tool_use` block with a JSON input →
  the SDK routes it over stdio JSON-RPC to our MCP server → the Python function
  runs → the return value comes back as a `tool_result` block Claude then reads.
- **Why `run_id`**: the orchestrator (`run_parking_agent`) mints a `run_id` and
  puts it in the prompt; the agent passes it to every tool. Evidence tools store
  their output under it; `evaluate_parking_request` reads that run's evidence.
  This makes the agent's orchestration operationally meaningful (the verdict
  uses the evidence *it* gathered) while keeping the evidence itself out of the
  model's hands.
- **Where AI ends**: once evidence is stored, deterministic Python decides
  legality and formats every date. Probabilistic model → deterministic software
  is the safety line.
