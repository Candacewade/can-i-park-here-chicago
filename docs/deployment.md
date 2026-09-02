# Deployment

Target: **$0/month** beyond the existing Claude Pro subscription.

| Piece | Host | Notes |
|---|---|---|
| Backend (FastAPI + agent + MCP + rules) | Render Free Web Service | one service; cold starts accepted |
| Frontend (React/Vite build) | Vercel Hobby | `VITE_API_URL` → Render URL |
| Daily monitor (Slice 4) | GitHub Actions `schedule:` | Render Free has no cron |
| Fast test suite | GitHub Actions on push/PR | agent evals stay manual |

## The runtime-agent auth question (Master Build Plan §51)

The Agent SDK authenticates by shelling out to the local **Claude Code CLI**,
which holds the Claude subscription credentials. That works on a developer
machine. On Render there is no logged-in CLI, and we will **not**:

- set `ANTHROPIC_API_KEY` / enable paid Claude API billing
- upload personal credential files or commit auth tokens

So the deployed backend degrades gracefully:

- `app/config.py:resolve_claude_cli()` returns `None` on Render
- `GET /api/health` reports `{"agent_runtime": false}`
- `POST /api/parking/analyze` returns **503** with a clear message
- everything deterministic still works; a future non-agent `/analyze/basic`
  could return the rule-engine result without the prose

Before enabling any remote agent runtime we re-verify the current supported
subscription-auth path. Preserving the $0 budget and account security beats
forcing the deployment.

## Environment variables

Backend (Render):

```
FRONTEND_ORIGINS=https://<your-app>.vercel.app
# do NOT set ANTHROPIC_API_KEY
# optional: SOCRATA_APP_TOKEN, AGENT_MODEL
```

Frontend (Vercel):

```
VITE_API_URL=https://<your-service>.onrender.com
```

Monitoring (GitHub Actions repo secrets, Slice 4):

```
WATCH_NOTIFY_MAP         JSON: { "wch_...": { "email": "..." } }  ← the only place emails live
GMAIL_APP_PASSWORD       Gmail app password for the sender account
GMAIL_SENDER             the sender address
CLAUDE_CODE_OAUTH_TOKEN  optional: `claude setup-token` output (subscription, NOT an API
                         key). Present -> scheduled emails are agent-composed. Absent ->
                         deterministic templates, alerts still fire. See monitoring.md.
```

The workflow uses the built-in `GITHUB_TOKEN` (with `permissions: contents:
write`) to commit `backend/watches.json` back — no PAT needed. A PAT
(`GH_WATCHES_TOKEN` + `GH_WATCHES_REPO`) is only needed if you also want the
**Render API** to write watches through the GitHub contents API; otherwise
`POST /api/watches` on Render returns `email_registered: false` and the operator
adds the entry to `WATCH_NOTIFY_MAP` by hand.

## Render notes

- ephemeral filesystem — nothing generated at runtime is persisted; the location
  registry ships in git
- spins down when idle; first request after a sleep is slow (acceptable)
- no paid plan, no persistent disk
