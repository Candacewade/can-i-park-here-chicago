# Proactive Monitoring  (Slice 4)

The interactive `/analyze` answers "can I park here right now?". Monitoring
answers it **for you, every day, until you move the car** — a morning status
email, urgent alerts when a time-sensitive risk appears, and move reminders.

## Concepts

**Watch** — a registered parked car (`app/monitor/models.py`):

| field | |
|---|---|
| `watch_id` | stable, anonymous — `wch_<12 hex>` — **the only identifier in the repo** |
| `location_id`, `start_time`, `end_time`, `permit_zone` | the request to monitor |
| `status` | `active` / `resolved` (moved / cancelled) / `expired` (`end_time` passed) |
| `created_at`, `last_decision`, `last_checked_at` | |
| `notified` | keys of messages already sent: `morning:<date>`, `urgent:<cause-hash>`, `reminder:3d`, `reminder:night` |

## Persistence — `$0`, no database, **no PII in the repo**

| what | where |
|---|---|
| watch state (the fields above, **no email**) | `backend/watches.json`, committed to the repo |
| `watch_id → {email}` map | `WATCH_NOTIFY_MAP` GitHub Actions **secret** (JSON), or a git-ignored `backend/notify_map.local.json` in dev — never committed |
| Gmail app password | `GMAIL_APP_PASSWORD` secret |

`app/monitor/store.py` picks a backend by env: `FileWatchStore` (a checkout — the
scheduled job, local dev) or `GitHubWatchStore` (the contents API — for the
FastAPI service on Render, which has no durable disk).

`POST /api/watches` creates the watch (state) and tries to register the email in
the local map. Where that isn't writable (Render), it returns
`email_registered: false` and a note: an operator must add the `watch_id → email`
entry to the `WATCH_NOTIFY_MAP` secret before notifications send. The monitor
still evaluates a watch with no destination — it just doesn't email.

## Daily run — GitHub Actions `schedule:` cron

`.github/workflows/monitor.yml` runs `python -m app.monitor --no-agent` (no
Claude CLI in CI → deterministic templates; alerts still send, only the prose
degrades) and commits `backend/watches.json` changes back. Cron
`0 13 * * *` ≈ 07:00–08:00 America/Chicago. `POST /api/monitor/run` (optionally
guarded by `X-Monitor-Token`) is an alternative trigger for an external pinger.

Per active watch, `app/monitor/run.py`:

```
1. DETERMINISTIC CORE: gather_evidence -> evaluate_parking -> decision + urgent_alert
2. app/monitor/schedule.py:due_messages(watch, decision, now)  -- purely deterministic:
     morning        -- once per calendar day
     urgent         -- iff decision.urgent_alert, once per distinct cause
     reminder 3d    -- exactly REMINDER_DAYS_AHEAD days before decision.move_by
     reminder night -- the evening before move_by (after REMINDER_NIGHT_BEFORE_HOUR)
3. if anything is due AND the agent runtime is available:
     run_parking_agent(request)  -- investigation wing (snow/weather, events,
     find_legal_parking_nearby) + prose; re-take the decision + due list
4. compose one email for the highest-priority due message
     (URGENT > night-before > 3d > morning); mark every due key notified
5. send via Gmail SMTP (or ./outbox/ with no credentials); persist watches
```

## The safety line

- **Deterministic decides whether an urgent alert is warranted.** `urgent_alert`
  comes straight from `evaluate_parking()`. The agent may reprioritize and word
  it; it cannot add or suppress the trigger.
- **The agent composes** the prose and owns soft content — the daily summary,
  "street cleaning is also due Thursday", the snow-risk narrative.
- No agent runtime ⇒ a plain deterministic template; the alert still goes out.

## Email

`app/services/email.py` — `smtplib` + STARTTLS to `smtp.gmail.com:587`, auth with
the app-password secret. ~500/day is ample. No `GMAIL_SENDER` /
`GMAIL_APP_PASSWORD` ⇒ the message is written to `backend/outbox/` instead.

## API surface

```
POST   /api/watches        { location_id, start_time, end_time, permit_zone, email }
                           -> { watch_id, email_registered, note }
GET    /api/watches/{id}    state only — no email echoed back
DELETE /api/watches/{id}    -> status: resolved
POST   /api/monitor/run     run the pass now (X-Monitor-Token if MONITOR_TOKEN set)
```
