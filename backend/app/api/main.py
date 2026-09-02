"""The FastAPI application.

    POST /api/parking/analyze     run the parking agent over a structured request
    GET  /api/locations           the selector tree for the frontend
    GET  /api/health              liveness (also warms a cold Render dyno)
    POST /api/watches             register a car-watch for daily monitoring
    GET  /api/watches/{id}        watch state (no email echoed back)
    DELETE /api/watches/{id}      stop monitoring a watch
    POST /api/monitor/run         trigger the daily pass (protected)

One process contains FastAPI + the Claude agent + the MCP server + rule engine
(Master Build Plan sec. 49).
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agent.parking_agent import AgentRunResult, run_parking_agent
from app.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CreateWatchRequest,
    CreateWatchResponse,
    ExampleAddress,
    MonitorRunResponse,
    ResolveRequest,
    ResolveResponse,
    SideCandidate,
    ToolCallView,
    WatchView,
)
from app.config import FRONTEND_ORIGINS, MONITOR_TOKEN, resolve_claude_cli
from app.locations.registry import LocationNotFoundError, get_location, remember_location
from app.locations.resolve import resolve_address
from app.models.decision import ParkingStatus
from app.models.requests import ParkingRequest
from app.monitor import notify
from app.monitor.models import Watch, WatchStatus
from app.monitor.run import run_monitor
from app.monitor.store import get_store

app = FastAPI(title="Can I Park Here? — Chicago", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["GET", "POST"],
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
    )


@app.post("/api/watches", response_model=CreateWatchResponse, status_code=201)
def create_watch(payload: CreateWatchRequest) -> CreateWatchResponse:
    try:
        get_location(payload.location_id)
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        watch = Watch(
            location_id=payload.location_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
            permit_zone=payload.permit_zone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    store = get_store()
    watches = store.load()
    watches[watch.watch_id] = watch
    store.save(watches)

    registered = notify.register_email(watch.watch_id, payload.email)
    note = (
        "Email registered for notifications."
        if registered
        else (
            "Watch created, but the private data store could not be written. An "
            f"operator must add {{\"{watch.watch_id}\": {{\"email\": \"...\"}}}} to "
            "the WATCH_NOTIFY_MAP secret before notifications will send."
        )
    )
    return CreateWatchResponse(
        watch_id=watch.watch_id, email_registered=registered, note=note
    )


@app.get("/api/watches/{watch_id}", response_model=WatchView)
def get_watch(watch_id: str) -> WatchView:
    watch = get_store().load().get(watch_id)
    if watch is None:
        raise HTTPException(status_code=404, detail="unknown watch")
    return _watch_view(watch)


@app.delete("/api/watches/{watch_id}", response_model=WatchView)
def delete_watch(watch_id: str) -> WatchView:
    store = get_store()
    watches = store.load()
    watch = watches.get(watch_id)
    if watch is None:
        raise HTTPException(status_code=404, detail="unknown watch")
    watch.status = WatchStatus.RESOLVED
    store.save(watches)
    notify.forget(watch_id)
    return _watch_view(watch)


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
