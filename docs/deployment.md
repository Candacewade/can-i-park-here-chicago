# Deployment

Target: **$0/month** beyond the existing Claude Pro subscription.

| Piece | Host | Notes |
|---|---|---|
| Backend (FastAPI + agent + MCP + rules) | Render Free Web Service | one service; cold starts accepted |
| Frontend (React/Vite build) | Vercel Hobby | `VITE_API_URL` → Render URL |
| Daily + hourly monitor | GitHub Actions `schedule:` (public repo → free minutes) | Render Free has no cron |
| **Runtime user data** | a **separate private GitHub repo** | watches / resolved blocks / notify map — never in this public repo |
| Fast test suite | GitHub Actions on push/PR | agent evals stay manual |

## Deploy — step by step

Secret names the code expects (align GitHub Actions secrets + Render env to
these exactly): `GH_DATA_REPO`, `GH_DATA_TOKEN`, `GMAIL_ADDRESS`,
`GMAIL_APP_PASSWORD`, and optionally `CLAUDE_CODE_OAUTH_TOKEN`, `MONITOR_TOKEN`,
`FRONTEND_ORIGINS`, `WATCH_NOTIFY_MAP`. (`GMAIL_SENDER` still works as a legacy
alias for `GMAIL_ADDRESS`.)

**1. Private data repo** (once). Create `<you>/can-i-park-here-chicago-data`
**with a README** (so the `main` branch exists). Create a **fine-grained PAT**:
repo access = *only that repo*, permissions = **Contents: Read and write**
(+ Metadata: read, which is automatic). Add `GH_DATA_REPO` + `GH_DATA_TOKEN` as
**repo Actions secrets** on the public repo.

**2. Verify the data repo** — locally, with the token in your shell:

```bash
cd backend
GH_DATA_REPO=<you>/can-i-park-here-chicago-data GH_DATA_TOKEN=github_pat_... \
  python scripts/check_data_repo.py        # -> "OK: ... readable and writable"
```

**3. Claude runtime token** (optional, for agent-composed emails). On your
machine: `claude setup-token` → a one-time browser flow → a subscription OAuth
token (**not** an API key). Add it as the repo Actions secret
`CLAUDE_CODE_OAUTH_TOKEN`. Without it the scheduled emails use deterministic
templates; alerts still fire.

**4. Backend → Render.** Sign in (free), New → **Blueprint** → connect this
repo; it reads `render.yaml` (free Python web service, `rootDir: backend`,
health check `/api/health`). In the dashboard set the `sync: false` values:
`GH_DATA_REPO`, `GH_DATA_TOKEN`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`
(`FRONTEND_ORIGINS` after step 5). **Do not** set `ANTHROPIC_API_KEY`. Note the
`onrender.com` URL.

**5. Frontend → Vercel.** Sign in (free), New Project → import this repo →
**Root Directory = `frontend`** (`vercel.json` handles the build). Env var
`VITE_API_URL` = the Render URL. Deploy; note the `*.vercel.app` URL, then set
Render's `FRONTEND_ORIGINS` to it and let Render redeploy.

**6. Verify.** `GET <render>/api/health` → `{"status":"ok","agent_available":false}`.
Open the Vercel URL, enter an address (e.g. `2400 N Clark St`, `60614`), confirm
the block + side, run the check — a `LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN`
result with `agent_available: false` and a deterministic explanation (no Claude
CLI on Render → no investigation/prose; the verdict is unaffected). In the
public repo → Actions → **Parking monitor (daily)** → *Run workflow* — it should
succeed and, if you have any watches, write to the private data repo.

Steps 3–5 need your accounts / browser sign-in / secure token entry — they
cannot be automated from here.

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

So the deployed backend degrades gracefully — **the agent is optional
enrichment, never a dependency of the parking check**:

- `app/config.py:resolve_claude_cli()` returns `None` on Render
- `GET /api/health` reports `{"agent_available": false}`
- `POST /api/parking/analyze` still resolves the location, runs the full
  deterministic gather + completeness + rule engine, and returns the verdict +
  `move_by` + a deterministic-template explanation, with `agent_available: false`
- when the CLI *is* available (locally, or on Render with Node +
  `CLAUDE_CODE_OAUTH_TOKEN`), the same endpoint additionally runs the agent for
  snow/weather context, nearby alternatives, and richer prose

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
GMAIL_ADDRESS             the sender address
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
