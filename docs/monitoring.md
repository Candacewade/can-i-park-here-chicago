# Proactive Monitoring  (Slice 4)

The interactive `/analyze` answers "can I park here right now?". Monitoring
answers it **for you, every day, until you move the car** — a morning status
email, urgent alerts when a time-sensitive risk appears, and move reminders.

## Concepts

**Watch** — a registered parked car (`app/monitor/models.py`):

| field | |
|---|---|
| `watch_id` | stable, anonymous — `wch_<12 hex>` |
| `manage_token` | opaque per-watch capability (`secrets.token_urlsafe`). The credential for unsubscribe / replace; embedded in that watch's own email links. Not PII. |
| `location_id`, `start_time`, `end_time`, `permit_zone` | the request to monitor |
| `status` | `active` / `resolved` (moved / cancelled / unsubscribed / replaced) / `expired` (`end_time` passed) |
| `created_at`, `last_decision`, `last_checked_at` | |
| `notified` | keys of messages already sent: `morning:<date>`, `urgent:<cause-hash>`, `reminder:3d`, `reminder:night` |

**Only an `active` watch ever notifies.** `resolved` and `expired` watches are
skipped by both scheduled passes — unsubscribing or replacing a spot stops all
future email immediately.

## Persistence — `$0`, no database, **no user data in the public repo**

All runtime user data lives in a **separate private GitHub repo**
(`<you>/can-i-park-here-chicago-data`), written through the same
`GitHubJsonStore` Contents API. Setup: [deployment.md](deployment.md).

| file (in the private repo) | contents |
|---|---|
| `watches.json` | anonymous `watch_id` + `manage_token` + block + interval + `status` + `notified` (no email) |
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
| `.github/workflows/monitor.yml` | `17 12 * * *` (12:17 UTC, ~06:17–07:17 CT) | **full** — morning summary, reminders, urgent | yes, when a runtime token is configured |
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
`GMAIL_APP_PASSWORD` ⇒ the message is written to `backend/outbox/` (`.txt` +
`.html`) instead.

Every message is **`multipart/alternative`**: a `text/plain` fallback and a
polished `text/html` body. `app/monitor/email_render.py` renders a typed node
list (`H1`/`H2`/`P`/`Panel`/`Finding`/`Rule`/`Actions`) to *both* — email-safe
inline CSS, semantic tags, a constrained 600px width, no images, no JS, real
`<h1>`/`<strong>`/`<hr>` hierarchy (never Markdown). `app/monitor/compose.py`
builds that node list: a **daily** template and an **urgent** template, each a
single cohesive document. The deterministic verdict is the skeleton; agent prose,
when present, fills exactly one "context / alternatives" section — it is never
appended as a second copy of the explanation. For `LEGAL_UNTIL` the restriction
that actually sets `move_by` is the one highlighted; later windows are summarised
in one line, not enumerated. Dynamic text is HTML-escaped; link params are
URL-encoded. The footer carries three capability-gated links — **Extend parking
time**, **Change parking spot**, **Stop monitoring this parking spot** — as plain
deep links / a confirmation page; none of them mutate on open.

## API surface

```
POST   /api/watches                    { location_id, start_time, end_time, permit_zone, email }
                                       -> { watch_id, manage_token, email_registered, note }
GET    /api/watches/{id}?token=...     state + location_summary + through_display (no email); token-gated
DELETE /api/watches/{id}?token=...     stop this watch -> status: resolved; token-gated
GET    /api/watches/{id}/unsubscribe?token=...   the link in every email -> confirmation page ONLY (no mutation)
POST   /api/watches/{id}/unsubscribe?token=...   the page's "Stop monitoring" button -> resolve + drop email
POST   /api/watches/{id}/replace       { token, location_id, start_time, end_time, permit_zone, email? }
                                       -> resolve old + create new in ONE store write
                                       -> { old_watch_id, watch_id, manage_token, email_registered }
POST   /api/watches/{id}/extend        { token, end_time }  -- SAME watch, later end only
                                       -> deterministic re-eval of the extended interval
                                       -> { watch_id, manage_token, end_time, through_display,
                                            status, move_by_display, urgent_alert, summary }
POST   /api/monitor/run                run the pass now (X-Monitor-Token if MONITOR_TOKEN set)
```

### Manage links & security

`watch_id` alone grants **nothing**: `GET`, `DELETE`, unsubscribe and `replace`
all require the watch's `manage_token`, checked with `secrets.compare_digest`; a
missing/wrong token returns the same `404` as an unknown id. The token is
124 bits of `token_urlsafe` entropy — not guessable — and scoped to one watch, so
it can never touch another. It lives in `watches.json` (private repo) and in that
watch's own email links; it is not a global secret and carries no personal data.

**The email unsubscribe link (`GET`) never mutates.** It only validates the
token and renders a *"Stop monitoring this parking spot?"* confirmation page with
a `Stop monitoring` / `Keep monitoring` choice. Only the explicit `POST` from
that page (same token, `?token=` query, empty body — no `multipart` dependency)
resolves the watch and drops its `notify_map` entry. A link scanner or client
prefetch of the `GET` therefore cannot unsubscribe anyone.

**Backwards compatibility.** Watches written before `manage_token` existed load
fine — `Watch.model_validate` mints one from the field default. `WatchStore.load()`
detects rows whose stored JSON lacked the key and re-saves the dict **once**, so
the minted token is stable for every later read and every email link. No manual
migration; no crash. (`test_pre_existing_watch_without_manage_token_is_backfilled`.)

### Extend parking time (`POST /api/watches/{id}/extend`)

Keep the **same watch** — location, side, `start_time`, `permit_zone`, recipient
email and `manage_token` are all untouched — and push `end_time` later.

1. `manage_token` checked (`compare_digest`); `404` on a wrong/foreign token.
2. watch must still be `ACTIVE` → else `409`.
3. new `end_time` must be strictly later than the current one → else `422`.
4. the deterministic engine re-evaluates the **extended** interval *before*
   anything is persisted (City data down ⇒ nothing changes); the response carries
   that verdict so the UI can immediately say "still clear" **or** "move by …".
   The LLM is not involved.
5. one `store.save`.

**`notified` after an extend.** The longer interval can surface a restriction
that was previously irrelevant, and it must still be able to notify:

| key | on extend | why |
|---|---|---|
| `reminder:3d`, `reminder:night` | **dropped** | they are relative to `move_by`, which the new window may have moved; keeping an already-sent key would suppress the reminder for the *new* deadline |
| `morning:<date>` | kept | the same calendar day needs no second summary — the UI already showed the new status, and tomorrow's summary reflects the new window |
| `urgent:<cause-hash>` | kept | an unchanged blocking cause must not re-alert. A **newly relevant** restriction produces a **different** `urgent_reason` → a different hash → not in `notified` → it fires normally |

So the smallest correct rule is: **drop `reminder:*`, keep everything else.**
Cause-hash dedup already does the rest. (`test_extend_drops_reminder_keys_keeps_morning_and_urgent`, `test_after_extend_new_restriction_reminder_fires`, `test_after_extend_unchanged_urgent_cause_not_resent`.)

**Change parking spot** = `POST /api/watches/{id}/replace`. The old watch flips to
`resolved` and the new one is written in a **single `store.save`**, so a partial
failure cannot leave both active. The new destination is registered *before* the
old mapping is forgotten (a crash between them still can't email — the old watch
is already `resolved`). The new watch starts with an empty `notified` list, so
dedup history never bleeds across locations. The recipient is reused from the old
mapping unless the request overrides `email`.

`API_BASE_URL` / `APP_BASE_URL` (env) are the absolute origins used to build the
email links. Unset ⇒ the links still render but aren't click-through from a mail
client; `APP_BASE_URL` falls back to the first non-localhost `FRONTEND_ORIGINS`.

### Frontend

`frontend/src/monitor.ts` owns persistence — `{watchId, token, email,
locationSummary, throughDisplay}` in `localStorage` (`ciph_monitor`), no account.

**Startup precedence** (`resolveStartupMonitor`): an explicit
`/?manage=<id>&token=<token>` email link identifies the watch the user wants to
manage *right now* and **wins over `localStorage`** — it is verified with
`GET /api/watches/{id}?token=…` before being adopted. If that watch is `active`
it replaces the stored monitor and the params are stripped from the URL; if it is
`resolved`/`expired` the app shows an inactive notice and **leaves the stored
watch untouched**; a `404` / bad-token link shows a small error and likewise
never clobbers a valid stored watch. With no link, `loadStoredMonitor()` restores
the stored active watch (refresh / new tab / return visit).

- **`MonitorBanner.tsx`** — a persistent card at the top of the home view
  whenever a monitor is active, *before and regardless of* any parking check:
  `🔔 Monitoring active` + block + through-date + **Change parking spot** /
  **Extend parking time** / **Stop monitoring**. "Extend" opens an inline panel
  (current end prefilled from `end_time_local`, new date/time) → `POST …/extend`
  → the banner shows *"✅ Monitoring extended"* plus the re-evaluated verdict
  ("still clear" or "move by …"), and `localStorage` + the "Through" line update.
  When the stored monitor lacks display fields (an email link on a fresh device),
  `App` hydrates them from `GET /api/watches/{id}?token=…` (`location_summary`,
  `through_display`, `end_time_local`); a `404` / non-`active` status ⇒ the stale
  localStorage entry is dropped. The email **Extend parking time** link
  (`/?manage=…&token=…&action=extend`) opens the banner straight into that panel.
- **`MonitorPanel.tsx`** — the result-tied card: **🔔 Monitor this parking
  spot** → email → `POST /api/watches` when there's no monitor; **Confirm move**
  → `POST …/replace` when "Change parking spot" has sent the user back through
  address → side → time → check. The **old watch stays active until the move is
  confirmed**.

## Production flows

### 1. Normal morning, nothing wrong

`monitor.yml` fires at 12:17 UTC → token present → installs the CLI →
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
