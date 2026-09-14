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
| `status` | `active` / `resolved` (moved / cancelled / unsubscribed / replaced) / `expired` (the calendar day `end_time` falls on has passed — see below) |
| `created_at`, `last_decision`, `last_checked_at` | |
| `notified` | keys of messages already sent: `morning:<date>`, `final_day:<date>`, `urgent:<cause-hash>`, `reminder:3d`, `reminder:night` |

**Expiry is calendar-day based, not instant-based.** A watch stays `active`
(and keeps being checked/emailed) through the *entire* calendar day
`end_time` falls on — that day gets one special `FINAL_DAY` email instead of
the ordinary `MORNING` one (see below) — and only flips to `expired` the day
after. This guarantees exactly one last message on a watch's final day rather
than the watch silently going quiet mid-morning once the precise `end_time`
instant passes (`app/monitor/run.py`).

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
| `.github/workflows/monitor.yml` | `17 8` + backups `17 9`, `37 9` UTC (targets ~06:17–07:17 CT delivery, ~4h earlier than that on the cron itself) | **full** — morning summary, reminders, urgent | yes, when a runtime token is configured |
| `.github/workflows/urgent.yml` | `9 * * * *` (hourly, offset from `:00`) | **urgent poll** — deterministic; acts only on a *new* urgent condition | only for a watch that has a new urgent condition |

The daily workflow runs three times a morning — a primary and two backups —
because GitHub sometimes delays or drops a scheduled run. `schedule.py`'s
`morning:<date>` dedup means a backup that fires after the primary already sent
does nothing: **still exactly one morning email per day.**

**Observed reality (checked via the Actions API, Sept 2–8):** GitHub's `schedule`
delivery for this repo has been delayed by **hours, not minutes** — the hourly
urgent poll (nominally every hour) has actually been firing every 2–6 hours, and
the daily morning pass landed as late as ~5.5 hours after its cron target. Each
job itself runs in well under a minute once GitHub actually starts it (no
code-side hang, no queue pileup, no cancelled runs) — the delay is entirely in
GitHub deciding when to fire the `schedule` event, which GitHub does not give any
SLA for. Because the delay affects this repo's scheduled events broadly rather
than one specific timestamp, adding more backup cron entries raises the odds of
*an* email arriving but does not make it arrive on time — all three tend to slip
by roughly the same number of hours together. Two things help: GitHub's own docs
flag the top of the hour as the highest-load slot, so `urgent.yml` no longer
fires at `:00`; and, as a blunter workaround, `monitor.yml`'s cron times are set
**~4 hours earlier** than the actual desired send time, so the observed delay
lands the real send close to the original intended morning window instead of
near noon. That's a workaround for the delay's observed *size*, not a fix for
the delay itself — if GitHub's behavior changes, these times will need
re-tuning, and there's no guarantee the delay stays close to 4 hours.

If the morning email must land at a dependable time regardless of how GitHub's
delay drifts, the durable fix is to stop depending on GitHub's `schedule`
trigger for that email and instead call **`POST /api/monitor/run`** from an
external, more punctual clock (see below) — `workflow_dispatch`/API-triggered
runs aren't subject to the same low-priority `schedule` queue.

The repo is public, so Actions minutes are free and unmetered. On a private repo
this is ~1,100 min/month (under the 2,000 free tier) — raise the hourly interval
if you register many watches.

`POST /api/monitor/run` (optionally guarded by `X-Monitor-Token`, set via the
`MONITOR_TOKEN` env var) is an alternative trigger for an external pinger — e.g.
a free service like cron-job.org hitting the deployed Render URL at a fixed
America/Chicago time. This is currently documented but not wired up to an
external pinger; nothing calls it on a schedule today.

### Full pass — `python -m app.monitor`

Per active watch, `app/monitor/run.py`:

```
1. DETERMINISTIC CORE: gather_evidence -> evaluate_parking -> decision + urgent_alert
2. app/monitor/schedule.py:due_messages(watch, decision, now)  -- purely deterministic:
     morning        -- once per calendar day, UNLESS today is the watch's
                        final day (see final_day) -- then this does not fire
     final_day      -- once, on the calendar day watch.end_time falls on;
                        replaces that day's morning message
     urgent         -- iff decision.urgent_alert, once per distinct cause hash
     reminder 3d    -- exactly REMINDER_DAYS_AHEAD days before decision.move_by
     reminder night -- the evening before move_by (after REMINDER_NIGHT_BEFORE_HOUR)
3. if anything is due AND the agent runtime is available:
     run_parking_agent(request)  -- investigation wing (snow/weather, events,
     find_legal_parking_nearby) + prose; re-take the decision + due list
4. compose one email for the highest-priority due message
     (URGENT > final_day > night-before > 3d > morning); mark every due key notified
5. send via Gmail SMTP (or ./outbox/ with no credentials); persist watches
```

**The final-day email** (`app/monitor/compose.py:_final_day_doc`) is the last
routine message a watch ever sends. It still reports today's actual
LEGAL/LEGAL_UNTIL/NOT_LEGAL/UNKNOWN status (the same body as the ordinary
daily check — `_status_nodes`, shared by both), framed with an explicit
choice: extend (the same "Extend parking time" link every email already
carries) or do nothing and the watch quietly expires tomorrow — no further
email until a new watch is created. A same-day `URGENT` alert still overrides
it (safety-critical alerts are never suppressed by the calendar cutoff).

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

### Self-reported override — the one deliberate exception to this line

`POST /api/watches/{id}/override` lets the user of one specific watch fully
replace its computed status with what they say they see in the real world
(e.g. a posted sign the city dataset doesn't reflect yet). **This is a real
exception to the line above, made knowingly, not a bug.** The rest of this
app's architecture (Master Build Plan §15, §0) exists specifically so nothing
but verified City data + the deterministic engine can decide legality — this
feature lets a human override that, for their own watch only, at their
explicit request.

- **Full override, either direction.** A report of NOT_LEGAL/LEGAL_UNTIL
  when city data says LEGAL is the expected case (a sign the data missed) and
  is safe by construction. A report of LEGAL when city data says NOT_LEGAL is
  *also* honored — if the user is wrong, the app will now tell them they're
  clear when they aren't. This was a considered choice after weighing
  narrower alternatives (e.g. "only allow reports that add restrictions,
  never remove them" — never let self-report produce false reassurance); the
  user chose full override anyway. `app/monitor/override.py` and
  `app/monitor/models.py:WatchOverride` carry that reasoning inline.
- **Scoped tight.** One watch, one person (whoever holds that watch's
  `manage_token`). Never written to city data, the rule engine, evaluations
  for other watches, or the `/api/parking/analyze` one-off check.
- **Always attributed.** Every email/UI surface showing an override-derived
  status says so explicitly ("Your own report — not verified city data") —
  never rendered as if it were a normal, verified check
  (`compose.py:_override_notice`).
- **Auto-expires.** `expires_at` is required on every report; there is no
  "forever" override. Past that time it's simply ignored
  (`override_active()`), no cleanup step needed.
- **Skips agent investigation.** `run.py` never calls the agent for a watch
  with an active override — the agent's investigation independently
  re-derives the real city-data verdict, which would silently fight with (and
  could overwrite) the override it's supposed to be superseding.
- Alerts still fire off an overridden decision exactly like a normal one — a
  self-reported NOT_LEGAL still sends the urgent email.

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
                                       -- if that email already has an ACTIVE watch on this
                                          exact location_id (double-click, retry, a second
                                          browser/device that doesn't know about the first),
                                          that watch is resolved and replaced by this one
                                          instead of leaving two active watches emailing
                                          independently. Different location_id -> untouched
                                          (tracking two spots with one email is legitimate).
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
POST   /api/watches/{id}/override      { token, status, move_by?, note, expires_at }
                                       -- self-reported, NOT verified -- see "The safety line"
                                       -> { watch_id, override, status, move_by_display, summary }
DELETE /api/watches/{id}/override?token=...   clear it -> back to verified city data
POST   /api/monitor/run                run the pass now (X-Monitor-Token if MONITOR_TOKEN set)

GET    /api/watches/by-email?email=... -> { watches: [...] }, each with its own manage_token
                                       -- NOT verified, see below
```

### "Find my watches" — manage by email, not by device

The home screen has an entry point ("Manage my parking watches") for someone
who is not on the device/browser that has a watch in `localStorage`: type an
email, immediately see and edit every active watch registered to it.

**This is intentionally NOT verified.** The first version of this feature
emailed a signed, time-limited link (extending the `manage_token`-mailed-to-you
trust model every other watch-management link in this app already uses) and
required clicking it before showing anything. In practice that confirmation
email wasn't arriving reliably enough to be usable, and the user explicitly
asked to drop the verification step rather than debug deliverability — `GET
/api/watches/by-email?email=...` (`notify.find_watch_ids_for_email`) now
returns every `ACTIVE` watch for an address, each with its own `manage_token`,
**as soon as the address is typed, with no proof of ownership required.**

**The trade-off, stated plainly:** anyone who knows or guesses an email
address that has been used with this app can view and cancel (or extend/move)
its watches. There is no login on this app to fall back on, so this is a real
exposure, not a theoretical one — accepted here for reliability over that
protection. If this needs to be revisited, the emailed-link version is a
straightforward re-add (git history has it: a stateless signed token in
`app/monitor/lookup_token.py`, a `POST /api/watches/lookup-request` endpoint,
`compose_lookup_email`) — the harder problem is almost certainly that a bare
"click this link" email (subject "🔑 Manage your parking watches") reads as a
phishing pattern to spam filters; a richer email or a one-time numeric code
typed back into the app might deliver more reliably than a link.

The frontend (`EmailWatchLookup.tsx` → `WatchesByEmailPanel.tsx`) renders one
card per watch with working **Extend** / **Stop monitoring** inline, and a
**Change parking spot** link that hands off to the existing single-watch flow
(`/?manage=<id>&token=...`) rather than re-implementing address search for a
list of watches.

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
| `final_day:<date>` | kept | extending ON the watch's final day (after that day's final-day email already went out) pushes `end_date` into the future — without this, `due_messages` would fall through to the (unsent) `morning:<date>` key and send a redundant same-day email right after the extend |
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
- **`EmailWatchLookup.tsx`** — always-visible home-screen card, independent of
  `localStorage` state: type an email, immediately renders
  `WatchesByEmailPanel` for it inline (no click-through, no verification —
  see "Find my watches" above for why).
- **`WatchesByEmailPanel.tsx`** — fetches `GET /api/watches/by-email`, one
  card per active watch with its own inline Extend / Stop monitoring, and a
  **Change parking spot** link that hands off to the existing single-watch
  `/?manage=<id>&token=…` flow rather than re-implementing address search here.
- **`OverrideReport.tsx`** — shared by `MonitorBanner` and
  `WatchesByEmailPanel`'s per-watch cards: no active override → a plain
  "Report what you see" link opens a small form (status, optional move-by,
  a required note, a required "applies until"); an active override → a
  visually distinct warn-toned box stating *"You reported this — not
  verified city data"* plus the note and expiry, and a **Clear my report**
  button. `MonitorBanner` fetches the override fresh via `GET
  /api/watches/{id}` on mount (it isn't kept in `localStorage` — it can
  change or expire on its own); `WatchesByEmailPanel`'s rows already have it
  from the list response.

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

### 4. The last day of the parking window

The watch's `end_time` is 9:00 AM today (Chicago).

```
now.date() == end_time.date()  -> watch stays ACTIVE (not yet expired)
due_messages -> [FINAL_DAY]  (not MORNING -- mutually exclusive by day)
compose_email(..., FINAL_DAY, prose)
    subject "🅿️ Today is the last day of your parking window"
    body: today's actual status (LEGAL/LEGAL_UNTIL/NOT_LEGAL/UNKNOWN) +
          "extend below, or do nothing and it stops after today"
send -> notified += ["final_day:<date>"]

next morning: now.date() > end_time.date() -> watch marked EXPIRED, no email,
  no further checks -- until the user sets up a new watch
```

If the user clicks **Extend parking time** later that same day, `end_time`
moves into the future; the next run that day now falls before the new
`end_date`, but `final_day:<date>` (kept by the extend endpoint, see below)
suppresses that day's `morning:<date>` key too, so extending doesn't also
trigger a redundant same-day summary.

### 5. Claude runtime unavailable

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

### 6. A self-reported override is active

City data says LEGAL. The user posted `POST /api/watches/{id}/override` with
`status=NOT_LEGAL` and a note describing a sign they saw, `expires_at` set to
tomorrow.

```
gather_evidence -> evaluate_parking -> LEGAL  (real, unchanged, city data)
override_active(watch, now) -> True
decision = decision_from_override(...)  -> NOT_LEGAL, urgent_alert=True
    (the real LEGAL decision is discarded for messaging purposes)
due_messages -> [URGENT]  (NOT_LEGAL is always urgent)
agent investigation SKIPPED (would re-derive the discarded LEGAL verdict)
compose_email(..., URGENT, prose=None, override=watch.override)
    subject "Urgent parking alert: Move your car now"
    body: "SOURCE: Your own report — not verified city data" notice up top,
          then the NOT_LEGAL template as normal (nearby alternative, etc.)
send -> notified += ["urgent:<hash of the override's note>"]

next day, after expires_at: override_active -> False
    -> decision reverts to the real (LEGAL) city-data verdict, no further
       mention of the override
```
