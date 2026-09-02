# Deployment

Target: **$0/month** beyond the existing Claude Pro subscription.

| Piece | Host | Notes |
|---|---|---|
| Backend (FastAPI + agent + MCP + rules) | Render Free Web Service | one service; cold starts accepted |
| Frontend (React/Vite build) | Vercel Hobby | `VITE_API_URL` → Render URL |
| Daily + hourly monitor | GitHub Actions `schedule:` (public repo → free minutes) | Render Free has no cron |
| **Runtime user data** | a **separate private GitHub repo** | watches / resolved blocks / notify map — never in this public repo |
| Fast test suite | GitHub Actions on push/PR | agent evals stay manual |

## Runtime user data — the private data repo

Resolved addresses, parked-car watches, and notification state are user data.
They must not land in this public code repo. They live in a **separate private
GitHub repo** (`<you>/can-i-park-here-chicago-data`), written through the same
`GitHubJsonStore` Contents API the project already uses.

One-time setup:

1. Create the private repo (empty is fine — files are created on first write).
2. Create a **fine-grained personal access token**: repository access = *only
   the data repo*; permissions = **Contents: Read and write**.
3. Set `GH_DATA_REPO` and `GH_DATA_TOKEN` as secrets on the public repo (for the
   workflows) and as env vars on Render (for the API).

Files in the private repo: `watches.json`, `blocks.json`, `notify_map.json`.
GitHub Free includes unlimited private repos; the Contents API and the PAT are
free; the workflows run in the *public* repo (unmetered minutes). Still **$0**.

**Without** `GH_DATA_*` (local dev): everything falls back to a git-ignored
`backend/.data/` directory. The public repo keeps only code, `fixtures.json`
(test-only), and any non-user geographic assets.

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
GH_DATA_REPO=<you>/can-i-park-here-chicago-data
GH_DATA_TOKEN=github_pat_...          fine-grained, Contents:rw on that repo only
# do NOT set ANTHROPIC_API_KEY
# optional: SOCRATA_APP_TOKEN, AGENT_MODEL, CLAUDE_CODE_OAUTH_TOKEN
```

Frontend (Vercel):

```
VITE_API_URL=https://<your-service>.onrender.com
```

Monitoring (GitHub Actions repo secrets):

```
GH_DATA_REPO             <you>/can-i-park-here-chicago-data
GH_DATA_TOKEN            fine-grained PAT, Contents:rw on the data repo only
GMAIL_APP_PASSWORD       Gmail app password for the sender account
GMAIL_SENDER             the sender address
CLAUDE_CODE_OAUTH_TOKEN  optional: `claude setup-token` output (subscription, NOT an API
                         key). Present -> scheduled emails are agent-composed. Absent ->
                         deterministic templates, alerts still fire.
WATCH_NOTIFY_MAP         optional seed/override for the notify map
```

The workflows write nothing to the public repo — no `GITHUB_TOKEN` write
permission, no commit step. All state goes to the private data repo via
`GH_DATA_TOKEN`. `POST /api/watches` on Render now registers the email straight
into the private repo (the Slice 4 "operator must edit a secret" limitation is
gone).

## Render notes

- ephemeral filesystem — nothing generated at runtime is persisted; the location
  registry ships in git
- spins down when idle; first request after a sleep is slow (acceptable)
- no paid plan, no persistent disk
