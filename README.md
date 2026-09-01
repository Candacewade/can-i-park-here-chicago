# Can I Park Here? — Chicago

I built a Chicago parking assistant that uses an **AI agent** to orchestrate
multiple authoritative parking-data tools exposed through a **custom MCP
server**. The system keeps legal parking decisions inside **deterministic rule
logic** rather than allowing the LLM to invent regulations, and (in progress)
includes **agent evaluations** that test tool selection, missing-data handling,
and hallucination prevention.

> Status: **Vertical Slice 1 complete.** A structured `ParkingRequest` flows
> through the Claude Agent SDK → our stdio MCP server → real City of Chicago
> Open Data, with every tool call visible. Rule engine, API, and UI are next.

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

- [docs/architecture.md](docs/architecture.md) — components and the safety boundary
- [docs/data-sources.md](docs/data-sources.md) — every dataset, fields, limitations
- [docs/MASTER_BUILD_PLAN.md](docs/MASTER_BUILD_PLAN.md) — the full project plan

## Roadmap

| Slice | Scope | State |
|---|---|---|
| 1 | `ParkingRequest` → agent → MCP → real data → visible result | ✅ |
| 2 | evidence completeness check + deterministic `evaluate_parking()` | next |
| 3 | React selector UI → FastAPI → agent → result UI | |
| 4 | agent tracing, evals, failure handling | |
| 5 | generated Chicago-wide block registry + more datasets + deploy | |
