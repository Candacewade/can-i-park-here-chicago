# Architecture

```
                 React selectors (neighborhood → street → block → side → times → permit)
                          │  typed ParkingRequest (location_id + interval + permit_zone)
                          ▼
                 FastAPI  POST /api/parking/analyze         [Slice 3]
                          │
                          ▼
        ┌─────────  Claude parking agent  (Claude Agent SDK, subscription auth)
        │                 │  decides WHICH evidence tools to call (passes a run_id)
        │                 ▼
        │        custom MCP server  (stdio JSON-RPC, app/mcp/server.py)
        │                 │  fixed "parking toolbox" — no arbitrary HTTP/FS/shell
        │                 ▼
        │        Python data clients  →  City of Chicago Open Data (SODA)
        │                 │  every failure ⇒ EvidenceStatus.UNAVAILABLE
        │                 ▼
        │        normalized typed evidence  (Pydantic)
        │                 ▼
        │        app.evidence_store   ── ephemeral, per-run, application-controlled
        │                 │  each evidence tool persists its own authoritative output
        │                 │  keyed by (run_id, category, block/interval args)
        │                 ▼
        │        evaluate_parking_request  reads the stored evidence
        │                 │  (never re-fetches, never trusts agent-relayed data)
        │                 ▼
        │        deterministic evidence-completeness check
        │                 │  required category missing / not VERIFIED ⇒ UNKNOWN
        │                 ▼
        └───────► deterministic rule engine  evaluate_parking()
                          │  the ONLY component that decides legality
                          ▼
                 ParkingDecision: LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN
                          ▼
                 Claude explains the verified decision (cannot change it)
                          ▼
                 structured response → result UI
```

## The safety boundary

The LLM **orchestrates**; it never **adjudicates**.

| Claude controls | Claude does **not** control |
|---|---|
| which MCP tools to call | whether parking is legal |
| tool-call arguments (from the canonical request) | the meaning of a restriction |
| tool-call order | what to do when evidence is missing |
| explaining the final decision in words | the evidence *content* (tools store their own output) |
|  | the `ParkingDecision.status` / `move_by` |
|  | date / weekday / time-zone math (backend emits `*_display` strings) |

The agent's orchestration is *operationally real* — the evaluator uses exactly
the evidence the agent's tool calls produced — but it cannot forge a `LEGAL`:
a skipped required tool = missing evidence = `UNKNOWN`. `UNAVAILABLE` /
`UNSUPPORTED` / not-gathered ⇒ `UNKNOWN`, never presented as success.

## Components

| Path | Role | Slice |
|---|---|---|
| `backend/app/models/` | `ParkingRequest`, evidence schemas, `ParkingDecision` | 1 |
| `backend/app/locations/` | canonical location registry (`location_id` → block) | 1 |
| `backend/app/services/` | plain Python clients over 3 City datasets; failure → `UNAVAILABLE` | 1–2 |
| `backend/app/evidence_store.py` | ephemeral per-run store; evidence tools write, evaluator reads | 2 |
| `backend/app/mcp/` | `handlers.py` (testable logic) + `server.py` (stdio MCP wrappers) | 1–2 |
| `backend/app/agent/` | Claude Agent SDK integration + tool-call tracing; generates the `run_id` | 1 |
| `backend/app/cli.py` | developer runner: one request → visible trace | 1 |
| `backend/app/rules/` | `check_completeness` + `evaluate_parking()`; `gather_evidence` (non-agent baseline) | 2 ✅ |
| `backend/app/api/` | FastAPI app | 3 |
| `frontend/` | React (Vite + TS) structured-selector UI | 3 |
| `backend/evals/` | agent evaluation scenarios + metrics | 4 |

## Runtime AI authentication

The Agent SDK shells out to the local **Claude Code CLI**, which carries the
Claude Pro subscription credentials. We deliberately do **not** set
`ANTHROPIC_API_KEY` and do not create a paid Claude API dependency.
`app/config.py:resolve_claude_cli()` locates the CLI (env var → PATH → bundled
editor extension binary). Deployment implications: see
[deployment.md](deployment.md).

## Deployment shape (target)

One Render Free Python service = FastAPI + agent + MCP + services + rule engine.
Frontend on Vercel Hobby. Generated registry data committed to git (Render's
filesystem is ephemeral). Additional monthly cost: **$0**.
