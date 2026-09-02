# Architecture

```
             React selectors (neighborhood → street → block → side → times → permit)
                      │  typed ParkingRequest (location_id + interval + permit_zone)
                      ▼
             FastAPI  POST /api/parking/analyze
                      │
                      ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │ DETERMINISTIC CORE   (pure Python, runs every time, no agent)     │
   │                                                                  │
   │   gather_evidence()   residential · street cleaning ·            │
   │                       temporary closures · winter-ban calendar   │
   │        │  every data-source failure ⇒ EvidenceStatus.UNAVAILABLE │
   │        ▼                                                          │
   │   check_completeness()   required categories are season-aware    │
   │        ▼                                                          │
   │   evaluate_parking()  →  ParkingDecision                         │
   │        status LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN           │
   │        move_by · *_display strings · hard-alert flags            │
   └──────────────────────────────────────────────────────────────────┘
                      │  decision + full evidence handed to the agent
                      ▼
   ┌─ AGENT · INVESTIGATION WING  (Claude Agent SDK, optional) ────────┐
   │   Claude decides whether the situation warrants extra digging:    │
   │     • winter / snow in the forecast → snow route + NWS weather    │
   │     • special-event venue nearby     → event-impact context      │
   │     • a closure result looks unusual → pull permit detail        │
   │     • user asks "where do I move?"   → find_legal_parking_nearby()│
   │   New evidence → per-run evidence store. If a deterministic       │
   │   trigger promoted a category to required, re-evaluate.          │
   └──────────────────────────────────────────────────────────────────┘
                      │
                      ▼
   ┌─ AGENT · COMMUNICATION WING ────────────────────────────────────┐
   │   prioritize · assess urgency · write the grounded explanation, │
   │   the daily email, the alert copy. Cannot change status/move_by.│
   └────────────────────────────────────────────────────────────────┘
                      │
                      ▼
             structured response → result UI     │     (Slice 4)
                                                 └── scheduled monitor:
                                                     morning email,
                                                     deterministic urgent alerts,
                                                     T-3d / night-before reminders
```

## The division of labor

| Deterministic code decides | The Claude agent decides |
|---|---|
| which evidence categories are **required** (season-aware) | whether an **optional** investigation is worth doing |
| the required-evidence **gather** (always runs) | snow/weather context, event context, unusual-closure detail |
| **evidence completeness** | which nearby blocks to offer when asked where to move |
| **legality**: `status`, `move_by`, `*_display` | **prioritization** and **urgency framing** |
| **hard urgent-alert triggers** (verified restriction, move required within an urgent window) | the **wording** of the alert, the explanation, the daily email |
| all date / weekday / time-zone formatting | soft, non-safety communication (summaries, heads-ups) |

The agent can **add** evidence and **phrase** outcomes. It cannot skip a safety
check (the core is unconditional), set a status, or decide an urgent alert fires.
`UNAVAILABLE` / `UNSUPPORTED` / a required-but-missing category ⇒ `UNKNOWN`,
never presented as success.

## Components

| Path | Role | Slice |
|---|---|---|
| `backend/app/models/` | `ParkingRequest`, evidence schemas, `ParkingDecision` | 1–3 |
| `backend/app/locations/` | canonical location registry (`location_id` → block) | 1 |
| `backend/app/services/` | plain Python clients per City dataset + NWS weather; failure → `UNAVAILABLE` | 1–3 |
| `backend/app/rules/gather.py` | **the** deterministic required-evidence gather (runs every request) | 2→3 |
| `backend/app/rules/completeness.py` | season-aware required categories + verification check | 2–3 |
| `backend/app/rules/engine.py` | `evaluate_parking()` + hard urgent-alert flags | 2–3 |
| `backend/app/rules/nearby.py` | `find_legal_parking_nearby()` (deterministic) | 3 |
| `backend/app/evidence_store.py` | ephemeral per-run store for the agent's optional evidence | 2–3 |
| `backend/app/mcp/` | MCP server: read core evidence + optional investigation tools | 1–3 |
| `backend/app/agent/` | Claude Agent SDK: investigation + communication wings; tracing | 1–3 |
| `backend/app/api/` | FastAPI (`/analyze`, `/locations`, `/health`) | 3 |
| `backend/app/monitor/` | watch model, daily run, email composition | 4 |
| `frontend/` | React (Vite + TS) structured-selector UI + result UI | 3 |

## Runtime AI authentication

The Agent SDK shells out to the local **Claude Code CLI**, which carries the
Claude Pro subscription credentials. We do **not** set `ANTHROPIC_API_KEY`.
`app/config.py:resolve_claude_cli()` locates the CLI. If it is absent (e.g. on
Render), `/api/parking/analyze` returns a clean 503 and the deterministic core
still answers via any non-agent path. See [deployment.md](deployment.md).

## Deployment shape (target)

One Render Free Python service = FastAPI + agent + MCP + services + rule engine.
Frontend on Vercel Hobby. Monitoring runs in GitHub Actions (Render Free has no
cron). Generated registry data committed to git. Additional monthly cost: **$0**.
