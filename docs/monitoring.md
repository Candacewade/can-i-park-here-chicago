# Proactive Monitoring  (Slice 4)

The interactive `/analyze` answers "can I park here right now?". Monitoring
answers it **for you, every day, until you move the car** — a morning status
email, urgent alerts when a time-sensitive risk appears, and move reminders.

## Concepts

**Watch** — a registered parked car (`app/monitor/models.py`):

| field | |
|---|---|
| `watch_id` | stable, anonymous — `wch_<12 hex>` |
| `location_id`, `start_time`, `end_time`, `permit_zone` | the request to monitor |
| `status` | `active` / `resolved` (moved / cancelled) / `expired` (`end_time` passed) |
| `created_at`, `last_decision`, `last_checked_at` | |
| `notified` | keys of messages already sent: `morning:<date>`, `urgent:<cause-hash>`, `reminder:3d`, `reminder:night` |

## Persistence — `$0`, no database, **no user data in the public repo**

All runtime user data lives in a **separate private GitHub repo**
(`<you>/can-i-park-here-chicago-data`), written through the same
`GitHubJsonStore` Contents API. Setup: [deployment.md](deployment.md).

| file (in the private repo) | contents |
|---|---|
| `watches.json` | anonymous `watch_id` + block + interval + `status` + `notified` (no email) |
| `blocks.json` | resolved-address cache (`location_id` → block) |
| `notify_map.json` | `watch_id → {email}` |

`app/json_store.py:data_store(name)` picks the backend: `GitHubJsonStore` (the
private repo, when `GH_DATA_REPO` + `GH_DATA_TOKEN` are set) or `FileJsonStore`
(a git-ignored `backend/.data/` dir, local dev). The public code repo keeps only
code + `fixtures.json` (test-only) + non-user geographic assets.

`POST /api/watches` writes the watch and the email straight into the private
repo — it works on Render now. If that write fails it returns
`email_registered: false`; the monitor still evaluates a watch with no
destination, it just doesn't email.

## Two scheduled workflows

Render Free has no cron, so both run in GitHub Actions (in this **public** repo →
free minutes). They share a `concurrency: group: parking-monitor`, so runs never
overlap on the private data files. The workflows write **nothing** to the public
repo — no `contents: write`, no commit step; state goes to the private repo via
`GH_DATA_TOKEN`.

| workflow | cron | mode | agent |
|---|---|---|---|
| `.github/workflows/monitor.yml` | `0 13 * * *` (~07:00–08:00 CT) | **full** — morning summary, reminders, urgent | yes, when a runtime token is configured |
| `.github/workflows/urgent.yml` | `0 * * * *` (hourly) | **urgent poll** — deterministic; acts only on a *new* urgent condition | only for a watch that has a new urgent condition |

The repo is public, so Actions minutes are free and unmetered. On a private repo
this is ~1,100 min/month (under the 2,000 free tier) — raise the hourly interval
if you register many watches.

`POST /api/monitor/run` (optionally guarded by `X-Monitor-Token`) is an
alternative trigger for an external pinger.

### Full pass — `python -m app.monitor`

Per active watch, `app/monitor/run.py`:

```
1. DETERMINISTIC CORE: gather_evidence -> evaluate_parking -> decision + urgent_alert
2. app/monitor/schedule.py:due_messages(watch, decision, now)  -- purely deterministic:
     morning        -- once per calendar day
     urgent         -- iff decision.urgent_alert, once per distinct cause hash
     reminder 3d    -- exactly REMINDER_DAYS_AHEAD days before decision.move_by
     reminder night -- the evening before move_by (after REMINDER_NIGHT_BEFORE_HOUR)
3. if anything is due AND the agent runtime is available:
     run_parking_agent(request)  -- investigation wing (snow/weather, events,
     find_legal_parking_nearby) + prose; re-take the decision + due list
4. compose one email for the highest-priority due message
     (URGENT > night-before > 3d > morning); mark every due key notified
5. send via Gmail SMTP (or ./outbox/ with no credentials); persist watches
```

### Urgent poll — `python -m app.monitor --urgent-only`

Same core, but `due_messages` is filtered to `URGENT` only. A watch whose
decision is fine, or whose urgent cause hash is already in `notified`, produces
**nothing** — no email, and `watches.json` is left byte-for-byte unchanged (no
noisy hourly writes). The agent is invoked *only* for a watch that has a new
urgent condition, and only if a runtime token is configured.

## Runtime AI in the scheduled workflows

The Agent SDK authenticates through the Claude Code CLI, not an API key. To run
it in GitHub Actions on the Claude subscription (Master Build Plan §2, §51):

1. On your machine, run **`claude setup-token`** — a one-time browser flow that
   mints a long-lived **subscription** OAuth token (not an API key; it draws
   from your subscription usage limits).
2. Add it as the repo secret **`CLAUDE_CODE_OAUTH_TOKEN`**.

The workflows then `npm install -g @anthropic-ai/claude-code` and run the
agent-enabled command. This is the mechanism the official
`anthropics/claude-code-action` uses; the token is an encrypted Actions secret
(same trust level as `GMAIL_APP_PASSWORD`), is never committed, and is revocable
(`claude logout` / regenerate).

**If you do not configure the token** (or if subscription auth from CI stops
being supported): the workflows run `--no-agent`. Every deterministic behavior is
unchanged — the verdict, `move_by`, the urgent trigger, and the emails all still
fire — only the prose drops to a fixed template. This is a real limitation of
the $0 constraint, stated here rather than pretended away. Do **not** switch to
`ANTHROPIC_API_KEY` to work around it.

The same applies to `POST /api/monitor/run` on Render: the agent path needs Node
+ the CLI + `CLAUDE_CODE_OAUTH_TOKEN` in the Render environment, otherwise it
degrades to templates.

## The safety line

- **Deterministic decides whether an urgent alert is warranted.** `urgent_alert`
  comes straight from `evaluate_parking()`. The agent may reprioritize and word
  it; it cannot add or suppress the trigger.
- **The agent composes** the prose and owns soft content — the daily summary,
  "street cleaning is also due Thursday", the snow-risk narrative.
- No agent runtime ⇒ a plain deterministic template; the alert still goes out.

## Email

`app/services/email.py` — `smtplib` + STARTTLS to `smtp.gmail.com:587`, auth with
the app-password secret. ~500/day is ample. No `GMAIL_ADDRESS` /
`GMAIL_APP_PASSWORD` ⇒ the message is written to `backend/outbox/` instead.

## API surface

```
POST   /api/watches        { location_id, start_time, end_time, permit_zone, email }
                           -> { watch_id, email_registered, note }
GET    /api/watches/{id}    state only — no email echoed back
DELETE /api/watches/{id}    -> status: resolved
POST   /api/monitor/run     run the pass now (X-Monitor-Token if MONITOR_TOKEN set)
```

## Production flows

### 1. Normal morning, nothing wrong

`monitor.yml` fires at 13:00 UTC → token present → installs the CLI →
`python -m app.monitor`.

```
gather_evidence -> evaluate_parking -> LEGAL, urgent_alert=False
due_messages -> [MORNING]                 (not seen yet today)
MORNING is due, agent runtime up -> run_parking_agent:
    agent sees LEGAL, decides no investigation is needed (0 tool calls, or a
    quick winter weather check) and writes a two-line "you're fine" note
compose_email(watch, decision, MORNING, prose)
    subject "Parking OK - W Wrightwood Ave"
send via Gmail -> notified += ["morning:2026-05-14"]
save watches.json to the private repo (last_decision, last_checked_at, notified changed)
```

### 2. Morning heads-up (a move is coming)

Same daily path. `evaluate_parking` → `LEGAL_UNTIL`, `move_by` Thursday 9 AM,
`urgent_alert=False` (more than 12 h away).

```
due_messages -> [MORNING]     (also [REMINDER_3D] on the one day that is exactly
                               3 days before move_by)
agent runs: may call find_legal_parking_nearby and mention the street-cleaning
    window; writes "legal now, plan to move by Thursday"
compose_email(..., MORNING, prose)
    subject "Move by Thursday, May 15, 2026 at 9:00 AM - W Wrightwood Ave"
    body: status, move_by_display, the reasons, nearby alternatives
send -> notified += ["morning:<date>"]  (and "reminder:3d" on that day)
```

### 3. A new urgent restriction appears later in the day

14:00 UTC — `urgent.yml` hourly poll → `python -m app.monitor --urgent-only`.

```
gather_evidence now sees a fresh Full-closure permit overlapping the interval
evaluate_parking -> NOT_LEGAL, urgent_alert=True,
    urgent_reason="A verified restriction prevents parking here for this request."
    cause hash -> "urgent:7f3a2b1c"
due_messages -> [..., URGENT];  filtered to [URGENT]
"urgent:7f3a2b1c" is NOT in watch.notified  -> a NEW urgent condition
  -> communication is warranted -> run_parking_agent for THIS watch:
       get_closure_detail (what/where/when), find_legal_parking_nearby, prose
compose_email(..., URGENT, prose)   subject "URGENT: A verified restriction ..."
send -> notified += ["urgent:7f3a2b1c"]  -> save watches.json (private repo)

15:00 poll: same NOT_LEGAL, same hash, hash already in notified
  -> due after filter is []  -> nothing sent, watches.json untouched (no write)

next 13:00 daily run: due_messages -> [MORNING, URGENT]; URGENT hash already
  sent -> effective [MORNING] -> the morning summary goes out (it still shows
  the NOT_LEGAL status), no duplicate urgent alert
```

### 4. Claude runtime unavailable

`CLAUDE_CODE_OAUTH_TOKEN` is not set (or auth fails at runtime, or the CLI is
missing). The workflow runs `python -m app.monitor --no-agent`; if a token was
set but the call throws, `run.py` catches it per-watch and continues.

```
every due message is still computed deterministically
compose_email(..., prose=None)  -> deterministic template
    + the deterministic find_legal_parking_nearby block appended for
      NOT_LEGAL / LEGAL_UNTIL / urgent
urgent alerts STILL fire (the trigger is deterministic) - only the wording is a
    fixed template
emails send via Gmail as normal
```
