# Proactive Monitoring  (Slice 4 — design)

The interactive `/analyze` answers "can I park here right now?". Monitoring
answers it **for you, every day, until you move the car** — a morning status
email, urgent alerts when a time-sensitive risk appears, and move reminders.

## Concepts

**Watch** — a registered parked car:

```
watch_id        stable, anonymous (e.g. "wch_7f3a9c2b")   ← the only identifier in the repo
location_id     canonical block
start_time      when the car was parked
end_time        when the driver plans to leave (the horizon we monitor to)
permit_zone     optional
created_at
status          active | resolved | expired
last_decision   the most recent ParkingDecision status
notified        which messages have already gone out (morning:<date>, reminder:t-3, reminder:night-before, alert:<hash>)
```

## Persistence — `$0`, no database, **no PII in the repo**

| What | Where |
|---|---|
| `watches.json` (the fields above, **no email**) | committed to the repo via the GitHub API |
| `watch_id → { email, ... }` notification map | GitHub Actions **secret** `WATCH_NOTIFY_MAP` (JSON), never committed |
| Gmail app password | GitHub Actions secret `GMAIL_APP_PASSWORD` |

The API writes `watches.json` through the GitHub contents API on
add/remove/resolve. The scheduled job reads it, updates `status` / `notified` /
`last_decision`, and commits the change back. Git history is the audit log.

## Daily run — GitHub Actions `schedule:` cron

`.github/workflows/monitor.yml` (Render Free has no cron). Each run, for every
`active` watch:

```
1. build the ParkingRequest from the watch
2. DETERMINISTIC CORE: gather → completeness → evaluate_parking()
      → ParkingDecision + urgent_alert flag
3. decide which messages are due (deterministic):
      • morning summary        — once per calendar day
      • urgent alert           — iff decision.urgent_alert and not already sent for this cause
      • reminder T-3 days      — 3 days before the earliest required move
      • reminder night-before  — the evening before the earliest required move
4. AGENT (per watch, only if step 3 has something to send):
      • investigation wing: snow/weather, nearby events, unusual closure detail
      • find_legal_parking_nearby() for alerts / reminders
      • communication wing: compose subject + body, set priority
5. send via Gmail SMTP; record in `notified`; commit `watches.json`
```

## The safety line in monitoring

- **Deterministic decides whether an urgent alert is warranted** — `urgent_alert`
  comes straight from `evaluate_parking()` (verified restriction forcing a move
  inside the urgent window). The agent may reprioritize wording and ordering; it
  cannot add or suppress the trigger.
- **The agent composes** every message and owns the soft content — daily
  summaries, "street cleaning is also due Thursday", "the forecast shows 3″ of
  snow and your block is a 2-inch route".
- If the agent runtime is unavailable in CI, alerts still go out with a plain
  deterministic template; only the prose degrades.

## Email

`app/services/email.py` — `smtplib` + STARTTLS to `smtp.gmail.com:587`, auth with
the app-password secret. Plain-text + minimal HTML. ~500/day limit is ample.
Local/dev with no secret ⇒ render to `./outbox/` instead of sending.

## API surface (Slice 4)

```
POST   /api/watches        { location_id, start_time, end_time, permit_zone, email }
                           → { watch_id }   (email goes only to the secret map, never the repo)
GET    /api/watches/{id}   status + last decision   (no email echoed back)
DELETE /api/watches/{id}   → resolved
POST   /api/monitor/run    protected; what the scheduled workflow calls
```
