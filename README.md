# Can I Park Here? — Chicago

I built a Chicago parking assistant that uses an **AI agent** to orchestrate
multiple authoritative parking-data tools exposed through a **custom MCP
server**. The system keeps legal parking decisions inside **deterministic rule
logic** rather than allowing the LLM to invent regulations, and (in progress)
includes **agent evaluations** that test tool selection, missing-data handling,
and hallucination prevention.

> Status: **Slices 1–2 complete; Slice 3 in progress.** A deterministic core
> (real City of Chicago Open Data → completeness check → rule engine) always
> returns `LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN` + `move_by` on its own. The
> Claude agent wraps that core with optional **investigation** (snow/weather,
> nearby events, alternatives) and **communication** (prioritization, plain-
> language explanation, and — Slice 4 — a daily monitoring email). The agent
> never decides legality or whether an urgent alert fires. See
> [docs/architecture.md](docs/architecture.md).

## What's interesting here

- **Claude Agent SDK**, authenticated through a Claude Pro subscription — no
  `ANTHROPIC_API_KEY`, no paid Claude API dependency.
- A **custom Python MCP server** (`app/mcp/server.py`) that exposes a small,
  fixed "parking toolbox" over stdio JSON-RPC — no arbitrary HTTP, filesystem,
  or shell access for the agent.
- **Real authoritative data**: City of Chicago Open Data Portal (Socrata/SODA),
  free, no key. A data-source failure becomes an explicit `UNAVAILABLE`, never a
  silent "no restriction".
- A **deterministic safety boundary**: the agent gathers evidence and explains
  results; a separate rule engine is the only thing that returns
  `LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN`.
- **Structured outputs** end to end (Pydantic), and **tool-call tracing** so
  every agent run is understandable.
- Runs at **$0/month** beyond the Claude Pro subscription.

## Try it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e "backend[dev]"

# You need the Claude Code CLI available (it carries your subscription auth).
cd backend
python -m app.cli --list
python -m app.cli \
  --location wrightwood-3300w-north \
  --start 2026-09-08T19:00:00-05:00 \
  --end   2026-09-09T11:00:00-05:00 \
  --permit 100
```

You'll see the agent choose MCP tools, call them against live City data, and
summarize the verified evidence.

## Docs

- [docs/architecture.md](docs/architecture.md) — components and the deterministic/agent division
- [docs/rule-engine.md](docs/rule-engine.md) — the deterministic verdict + urgent-alert pipeline
- [docs/agent-design.md](docs/agent-design.md) — the agent's investigation + communication wings
- [docs/data-sources.md](docs/data-sources.md) — every dataset, fields, limitations
- [docs/mcp-tools.md](docs/mcp-tools.md) · [docs/monitoring.md](docs/monitoring.md) · [docs/deployment.md](docs/deployment.md)
- [docs/MASTER_BUILD_PLAN.md](docs/MASTER_BUILD_PLAN.md) — the full project plan (see §0 for the revision)

## Roadmap

| Slice | Scope | State |
|---|---|---|
| 1 | `ParkingRequest` → agent → MCP → real data → visible result | ✅ |
| 2 | deterministic completeness check + `evaluate_parking()`; per-run evidence store | ✅ |
| 3 | agent-role inversion (deterministic core always runs) + snow/weather + events + nearby-parking + FastAPI `/analyze` + React UI | in progress |
| 4 | proactive monitoring: watches, daily email, deterministic urgent alerts, move reminders | |
| 5 | generated Chicago-wide block registry + more datasets + deploy + polish | |
