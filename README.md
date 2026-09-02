# Can I Park Here? — Chicago

I built a Chicago parking assistant that uses an **AI agent** to orchestrate
multiple authoritative parking-data tools exposed through a **custom MCP
server**. The system keeps legal parking decisions inside **deterministic rule
logic** rather than allowing the LLM to invent regulations, and includes an
**agent evaluation suite** that tests tool selection, missing-data handling, and
hallucination prevention against pinned City data.

> Status: **Slices 1–6 complete — deployable.** A deterministic core (real City
> of Chicago Open Data → completeness check → rule engine) always returns
> `LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN` + `move_by` + a hard urgent-alert
> flag on its own. The Claude agent wraps that core with optional
> **investigation** (snow/weather via NWS, nearby events, unusual closures,
> `find_legal_parking_nearby`) and **communication** (prioritization, plain-
> language explanation). You enter an **exact Chicago address**; the backend
> resolves it (US Census geocoder + official City geometry) to the canonical
> block, side, sweeping ward/section, and every applicable dataset. A **daily +
> hourly GitHub Actions monitor** re-checks registered car-watches and emails a
> morning summary, deterministically-triggered urgent alerts, and move reminders.
> $0/month.
> See [docs/architecture.md](docs/architecture.md) · [docs/location-model.md](docs/location-model.md) · [docs/monitoring.md](docs/monitoring.md).

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

cd backend && uvicorn app.api.main:app --port 8000   # backend
cd ../frontend && npm install && npm run dev          # http://localhost:5173
# then enter an address, e.g. 2400 N Clark St / 60614
```

You'll see the address resolve to a canonical block, the deterministic core
decide, the agent optionally investigate (snow, events, alternatives), and a
grounded explanation — with every tool call visible in the agent-run inspector.
The agent runs locally (via your Claude subscription through the Claude Code
CLI); deploy notes are in [docs/deployment.md](docs/deployment.md).

## Docs

- [docs/architecture.md](docs/architecture.md) — components and the deterministic/agent division
- [docs/rule-engine.md](docs/rule-engine.md) — the deterministic verdict + urgent-alert pipeline
- [docs/agent-design.md](docs/agent-design.md) — the agent's investigation + communication wings
- [docs/data-sources.md](docs/data-sources.md) — every dataset, fields, limitations
- [docs/location-model.md](docs/location-model.md) — address → canonical block + side
- [docs/mcp-tools.md](docs/mcp-tools.md) · [docs/monitoring.md](docs/monitoring.md) · [docs/deployment.md](docs/deployment.md) · [docs/evaluations.md](docs/evaluations.md)
- [docs/MASTER_BUILD_PLAN.md](docs/MASTER_BUILD_PLAN.md) — the full project plan (see §0 for the revision)

## Roadmap

| Slice | Scope | State |
|---|---|---|
| 1 | `ParkingRequest` → agent → MCP → real data → visible result | ✅ |
| 2 | deterministic completeness check + `evaluate_parking()`; per-run evidence store | ✅ |
| 3 | agent-role inversion (deterministic core always runs) + snow/weather + events + nearby-parking + FastAPI `/analyze` + React UI | ✅ |
| 4 | proactive monitoring: watches, daily + hourly runs, deterministic urgent alerts, move reminders | ✅ |
| 5 | exact-address location resolution (Census geocoder + City geometry); deploy config; private data repo; graceful degradation without Claude | ✅ |
| 6 | agent evaluation suite ([docs/evaluations.md](docs/evaluations.md)) | ✅ |
