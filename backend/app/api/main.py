"""The FastAPI application.

    POST /api/parking/analyze     run the parking agent over a structured request
    GET  /api/locations           the selector tree for the frontend
    GET  /api/health              liveness (also warms a cold Render dyno)
    POST /api/watches                     register a car-watch for daily monitoring
    GET  /api/watches/{id}                watch state (token-gated, no email echoed back)
    DELETE /api/watches/{id}              stop monitoring a watch (token-gated)
    GET  /api/watches/{id}/unsubscribe    email link -> confirmation page (no mutation)
    POST /api/watches/{id}/unsubscribe    confirm -> resolve the watch, drop its email
    POST /api/watches/{id}/replace        move the monitored spot (resolve old + create new)
    POST /api/watches/{id}/extend         push the end_time later on the SAME watch
    POST /api/monitor/run                 trigger the daily pass (protected)

One process contains FastAPI + the Claude agent + the MCP server + rule engine
(Master Build Plan sec. 49).
"""

from __future__ import annotations

import html
import json
import secrets
from datetime import datetime
from urllib.parse import quote

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.agent.parking_agent import AgentRunResult, run_parking_agent
from app.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CreateWatchRequest,
    CreateWatchResponse,
    ExampleAddress,
    ExtendWatchRequest,
    ExtendWatchResponse,
    MonitorRunResponse,
    ReplaceWatchRequest,
    ReplaceWatchResponse,
    ResolveRequest,
    ResolveResponse,
    SideCandidate,
    ToolCallView,
    WatchView,
)
from app.config import (
    APP_BASE_URL,
    CHICAGO_TZ,
    FRONTEND_ORIGINS,
    MONITOR_TOKEN,
    resolve_claude_cli,
)
from app.locations.registry import LocationNotFoundError, get_location, remember_location
from app.locations.resolve import resolve_address
from app.models.decision import ParkingStatus
from app.models.requests import ParkingRequest
from app.monitor import notify
from app.monitor.models import Watch, WatchStatus
from app.monitor.run import run_monitor
from app.monitor.store import get_store
from app.rules.engine import _display as _display_ct  # America/Chicago long-form label
from app.rules.engine import evaluate_parking
from app.rules.gather import gather_evidence

app = FastAPI(title="Can I Park Here? — Chicago", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "agent_available": resolve_claude_cli() is not None}


_EXAMPLES = [
    ExampleAddress(label="Lincoln Park", number=2400, street="N Clark St", zip_code="60614"),
    ExampleAddress(label="Logan Square", number=3300, street="W Wrightwood Ave", zip_code="60647"),
    ExampleAddress(label="Wicker Park", number=1600, street="N Damen Ave", zip_code="60647"),
]


@app.get("/api/locations/examples", response_model=list[ExampleAddress])
def location_examples() -> list[ExampleAddress]:
    return _EXAMPLES


@app.post("/api/locations/resolve", response_model=ResolveResponse)
def resolve(payload: ResolveRequest) -> ResolveResponse:
    resolved = resolve_address(
        payload.number, payload.street.strip(), payload.zip_code.strip(), payload.side
    )
    for loc in resolved.locations.values():
        remember_location(loc)

    suggested = resolved.suggested
    return ResolveResponse(
        in_chicago=resolved.in_chicago,
        matched_address=resolved.matched_address,
        street_name=suggested.street_name if suggested else None,
        neighborhood=resolved.neighborhood,
        from_cross_street=suggested.from_cross_street if suggested else None,
        to_cross_street=suggested.to_cross_street if suggested else None,
        street_sweeping_ward=suggested.street_sweeping_ward if suggested else None,
        street_sweeping_section=suggested.street_sweeping_section if suggested else None,
        latitude=suggested.latitude if suggested else None,
        longitude=suggested.longitude if suggested else None,
        suggested_side=resolved.suggested_side,
        side_confidence=resolved.side_confidence,
        side_options=[
            SideCandidate(side=s, location_id=loc.location_id, summary=loc.human_summary())
            for s, loc in resolved.locations.items()
        ],
        notes=resolved.notes,
    )


def _status(value: str | None) -> ParkingStatus:
    try:
        return ParkingStatus(value) if value else ParkingStatus.UNKNOWN
    except ValueError:
        return ParkingStatus.UNKNOWN


def _to_response(result: AgentRunResult) -> AnalyzeResponse:
    payload = result.decision or result.core_decision or {}
    decision = payload.get("decision") or {}
    completeness = payload.get("completeness") or {}
    status = _status(decision.get("status"))
    core_status = _status((result.core_decision or {}).get("decision", {}).get("status"))

    trace = [
        ToolCallView(
            order=call.order,
            name=call.short_name(),
            status="error" if call.is_error else "ok",
            latency_ms=call.latency_ms,
            arguments=call.arguments,
            result_preview=(json.dumps(call.result)[:400] if call.result is not None else ""),
        )
        for call in result.tool_calls
    ]

    summary = result.final_text.strip() or (
        "The deterministic decision is below; the agent did not add an explanation."
    )

    return AnalyzeResponse(
        status=status,
        move_by=decision.get("move_by"),
        start_time_display=decision.get("start_time_display"),
        end_time_display=decision.get("end_time_display"),
        move_by_display=decision.get("move_by_display"),
        urgent_alert=bool(decision.get("urgent_alert")),
        urgent_reason=decision.get("urgent_reason"),
        summary=summary,
        reasons=decision.get("reasons", []),
        unknown_reasons=decision.get("unknown_reasons", []),
        completeness_complete=bool(
            completeness.get("complete", status is not ParkingStatus.UNKNOWN)
        ),
        core_status=core_status,
        agent_available=result.agent_available,
        run_id=result.run_id,
        model=result.model,
        duration_ms=result.duration_ms,
        trace=trace,
    )


@app.post("/api/parking/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    """Always returns a deterministic parking decision. When the Claude runtime
    is available it also runs the agent for optional investigation + richer
    prose; when it is not, `agent_available` is false and the explanation is a
    deterministic template. The checker never goes down with the AI layer."""
    try:
        request = ParkingRequest(
            location_id=payload.location_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
            permit_zone=payload.permit_zone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = await run_parking_agent(request)  # degrades gracefully, never raises here
    return _to_response(result)


# --- watches / monitoring (Slice 4) ---------------------------------

def _watch_view(w: Watch) -> WatchView:
    try:
        summary = get_location(w.location_id).human_summary()
    except Exception:
        summary = None
    return WatchView(
        watch_id=w.watch_id,
        location_id=w.location_id,
        start_time=w.start_time,
        end_time=w.end_time,
        permit_zone=w.permit_zone,
        status=w.status.value,
        created_at=w.created_at,
        last_decision=w.last_decision,
        last_checked_at=w.last_checked_at,
        notified_count=len(w.notified),
        location_summary=summary,
        through_display=_display_ct(w.end_time),
        end_time_local=_local_wall(w.end_time),
    )


def _local_wall(dt: datetime) -> str:
    """'YYYY-MM-DDTHH:MM' in America/Chicago -- what the date/time inputs expect."""
    return dt.astimezone(CHICAGO_TZ).strftime("%Y-%m-%dT%H:%M")


def _new_watch(location_id: str, start_time, end_time, permit_zone: str | None) -> Watch:
    try:
        get_location(location_id)
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return Watch(
            location_id=location_id,
            start_time=start_time,
            end_time=end_time,
            permit_zone=permit_zone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _require_watch(watch_id: str, token: str | None, watches: dict) -> Watch:
    """Look a watch up and check the management token in constant time. A wrong
    or missing token gets the same 404 as an unknown id -- knowing an id alone
    reveals nothing and grants nothing."""
    watch = watches.get(watch_id)
    if (
        watch is None
        or not token
        or not token.isascii()
        or not secrets.compare_digest(token, watch.manage_token)
    ):
        raise HTTPException(status_code=404, detail="unknown watch or bad token")
    return watch


_STORE_WRITE_FAILED = (
    "Watch saved, but the private data store could not be written. Set "
    "GH_DATA_REPO / GH_DATA_TOKEN (or WATCH_NOTIFY_MAP) so notifications can send."
)


@app.post("/api/watches", response_model=CreateWatchResponse, status_code=201)
def create_watch(payload: CreateWatchRequest) -> CreateWatchResponse:
    watch = _new_watch(
        payload.location_id, payload.start_time, payload.end_time, payload.permit_zone
    )
    store = get_store()
    watches = store.load()
    watches[watch.watch_id] = watch
    store.save(watches)

    registered = notify.register_email(watch.watch_id, payload.email)
    return CreateWatchResponse(
        watch_id=watch.watch_id,
        manage_token=watch.manage_token,
        email_registered=registered,
        note="Email registered for notifications." if registered else _STORE_WRITE_FAILED,
    )


@app.get("/api/watches/{watch_id}", response_model=WatchView)
def get_watch(watch_id: str, token: str | None = Query(default=None)) -> WatchView:
    return _watch_view(_require_watch(watch_id, token, get_store().load()))


def _resolve_watch(watch_id: str, token: str | None) -> Watch:
    """Shared by DELETE and the email unsubscribe link: mark this one watch
    resolved and drop its notification mapping. Idempotent."""
    store = get_store()
    watches = store.load()
    watch = _require_watch(watch_id, token, watches)
    if watch.status is WatchStatus.ACTIVE:
        watch.status = WatchStatus.RESOLVED
        store.save(watches)
    notify.forget(watch_id)
    return watch


@app.delete("/api/watches/{watch_id}", response_model=WatchView)
def delete_watch(watch_id: str, token: str | None = Query(default=None)) -> WatchView:
    return _watch_view(_resolve_watch(watch_id, token))


_PAGE_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
)


def _unsub_shell(title: str, inner: str, status: int) -> HTMLResponse:
    body = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title></head>"
        f'<body style="margin:0;background:#eef0f3;font-family:{_PAGE_FONT};">'
        '<div style="max-width:460px;margin:64px auto;background:#fff;border-radius:10px;'
        f'padding:32px;text-align:center;">{inner}</div></body></html>'
    )
    return HTMLResponse(content=body, status_code=status)


def _unsub_message(title: str, message: str, ok: bool) -> HTMLResponse:
    inner = (
        f'<div style="font-size:40px;">{"✅" if ok else "⚠️"}</div>'
        f'<h1 style="font-size:20px;color:#1a1a1a;margin:12px 0 8px;">{html.escape(title)}</h1>'
        f'<p style="font-size:15px;color:#444;line-height:1.5;">{html.escape(message)}</p>'
    )
    return _unsub_shell(title, inner, 200 if ok else 404)


@app.get("/api/watches/{watch_id}/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(watch_id: str, token: str | None = Query(default=None)) -> HTMLResponse:
    """The link in every email. Validates the capability and shows a confirmation
    page -- it does NOT change anything (so a link scanner / prefetch cannot
    unsubscribe you). The explicit POST below does the work."""
    try:
        _require_watch(watch_id, token, get_store().load())
    except HTTPException:
        return _unsub_message(
            "This link is not valid",
            "We couldn't open the unsubscribe page. The link may be old -- use the "
            "one in your most recent parking email.",
            ok=False,
        )
    action = f"/api/watches/{html.escape(watch_id)}/unsubscribe?token={quote(token or '')}"
    keep = html.escape(APP_BASE_URL or "/")
    inner = (
        '<div style="font-size:40px;">🔔</div>'
        '<h1 style="font-size:20px;color:#1a1a1a;margin:12px 0 8px;">'
        "Stop monitoring this parking spot?</h1>"
        '<p style="font-size:15px;color:#444;line-height:1.5;margin-bottom:24px;">'
        "You will no longer get daily status checks or urgent move-your-car alerts "
        "for this spot. You can start again any time from the app.</p>"
        f'<form method="post" action="{action}" style="margin:0;">'
        '<button type="submit" style="font:inherit;font-weight:600;padding:12px 20px;'
        'border:0;border-radius:8px;background:#c62828;color:#fff;cursor:pointer;">'
        "Stop monitoring</button></form>"
        f'<p style="margin:16px 0 0;"><a href="{keep}" '
        'style="color:#0b63c5;font-size:14px;">Keep monitoring</a></p>'
    )
    return _unsub_shell("Stop monitoring this parking spot?", inner, 200)


@app.post("/api/watches/{watch_id}/unsubscribe", response_class=HTMLResponse)
def unsubscribe_confirm(
    watch_id: str, token: str | None = Query(default=None)
) -> HTMLResponse:
    """Explicit confirmation from the page above. Requires the same manage_token."""
    try:
        _resolve_watch(watch_id, token)
    except HTTPException:
        return _unsub_message(
            "This link is not valid",
            "We couldn't turn off monitoring. Use the link in your most recent "
            "parking email.",
            ok=False,
        )
    return _unsub_message(
        "Parking monitoring has been turned off",
        "You won't get any more daily or urgent emails for this parking spot. "
        "You can start monitoring again any time from the app.",
        ok=True,
    )


@app.post("/api/watches/{watch_id}/replace", response_model=ReplaceWatchResponse)
def replace_watch(watch_id: str, payload: ReplaceWatchRequest) -> ReplaceWatchResponse:
    """Move the monitored spot. Resolve the old watch and create a fresh one in a
    single store write, so a partial failure can never leave both active."""
    store = get_store()
    watches = store.load()
    old = _require_watch(watch_id, payload.token, watches)

    new = _new_watch(
        payload.location_id, payload.start_time, payload.end_time, payload.permit_zone
    )
    recipient = payload.email or notify.get_email(old.watch_id)

    # one atomic write: old -> resolved, new -> active (fresh notified history)
    old.status = WatchStatus.RESOLVED
    watches[new.watch_id] = new
    store.save(watches)

    # register the new destination BEFORE forgetting the old, so a crash between
    # them still leaves the (already-resolved) old watch unable to email.
    registered = notify.register_email(new.watch_id, recipient) if recipient else False
    notify.forget(old.watch_id)

    return ReplaceWatchResponse(
        old_watch_id=old.watch_id,
        watch_id=new.watch_id,
        manage_token=new.manage_token,
        email_registered=registered,
    )


_EXTEND_SUMMARY = {
    ParkingStatus.LEGAL: "Your parking is still clear through the new end time.",
    ParkingStatus.LEGAL_UNTIL: "Your extended stay changes your parking status — "
    "you'll need to move by {move_by}.",
    ParkingStatus.NOT_LEGAL: "Your extended stay is not legal here. {reason}",
    ParkingStatus.UNKNOWN: "We couldn't verify parking for the extended window.",
}


@app.post("/api/watches/{watch_id}/extend", response_model=ExtendWatchResponse)
def extend_watch(watch_id: str, payload: ExtendWatchRequest) -> ExtendWatchResponse:
    """Push the end of the parking window later on the SAME watch. Location, side,
    start time, permit, recipient email and manage_token are all untouched."""
    store = get_store()
    watches = store.load()
    watch = _require_watch(watch_id, payload.token, watches)
    if watch.status is not WatchStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="this watch is no longer active")

    new_end = payload.end_time
    if new_end.tzinfo is None:
        new_end = new_end.replace(tzinfo=CHICAGO_TZ)
    if new_end <= watch.end_time:
        raise HTTPException(
            status_code=422, detail="the new end time must be later than the current end time"
        )

    # Re-evaluate the EXTENDED interval first -- if the City data is unavailable we
    # fail before persisting anything.
    request = ParkingRequest(
        location_id=watch.location_id,
        start_time=watch.start_time,
        end_time=new_end,
        permit_zone=watch.permit_zone,
    )
    decision = evaluate_parking(request, gather_evidence(request))

    watch.end_time = new_end
    # notified: the reminder keys are relative to move_by, which the longer window
    # may have changed -- drop them so a T-3d / night-before reminder for the new
    # deadline can still fire. morning:<date> and urgent:<cause-hash> stay: a same
    # calendar day needs no second summary, and an unchanged urgent cause must not
    # re-alert. A NEW restriction produces a NEW cause hash and notifies normally.
    watch.notified = [k for k in watch.notified if not k.startswith("reminder:")]
    watch.last_decision = decision.status.value
    watch.last_checked_at = datetime.now(tz=CHICAGO_TZ)
    store.save(watches)

    reason = decision.urgent_reason or "a verified restriction applies"
    summary = _EXTEND_SUMMARY[decision.status].format(
        move_by=decision.move_by_display or "your deadline", reason=reason
    )
    return ExtendWatchResponse(
        watch_id=watch.watch_id,
        manage_token=watch.manage_token,
        end_time=watch.end_time,
        end_time_local=_local_wall(watch.end_time),
        through_display=_display_ct(watch.end_time),
        status=decision.status,
        start_time_display=decision.start_time_display,
        end_time_display=decision.end_time_display,
        move_by_display=decision.move_by_display,
        urgent_alert=decision.urgent_alert,
        summary=summary,
    )


@app.post("/api/monitor/run", response_model=MonitorRunResponse)
async def monitor_run(x_monitor_token: str | None = Header(default=None)) -> MonitorRunResponse:
    if MONITOR_TOKEN and x_monitor_token != MONITOR_TOKEN:
        raise HTTPException(status_code=401, detail="bad or missing X-Monitor-Token")
    report = await run_monitor(use_agent=resolve_claude_cli() is not None)
    return MonitorRunResponse(
        ran_at=report.ran_at,
        checked=report.checked,
        emails_sent=report.emails_sent,
        summary=report.summary(),
    )
