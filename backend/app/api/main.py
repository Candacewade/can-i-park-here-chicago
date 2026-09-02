"""The FastAPI application.

    POST /api/parking/analyze   run the parking agent over a structured request
    GET  /api/locations         the selector tree for the frontend
    GET  /api/health            liveness (also useful to warm a cold Render dyno)

One process contains FastAPI + the Claude agent + the MCP server + rule engine
(Master Build Plan sec. 49).
"""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agent.parking_agent import AgentAuthError, AgentRunResult, run_parking_agent
from app.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BlockOption,
    LocationsResponse,
    NeighborhoodOption,
    SideOption,
    StreetOption,
    ToolCallView,
)
from app.config import FRONTEND_ORIGINS, resolve_claude_cli
from app.locations.registry import list_locations, registry_summary
from app.models.decision import ParkingStatus
from app.models.requests import ParkingRequest

app = FastAPI(title="Can I Park Here? — Chicago", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "agent_runtime": resolve_claude_cli() is not None}


@app.get("/api/locations", response_model=LocationsResponse)
def locations() -> LocationsResponse:
    summary = registry_summary()
    tree: dict[str, dict[str, dict[tuple[str, str], list[SideOption]]]] = {}
    for loc in list_locations():
        streets = tree.setdefault(loc.neighborhood, {})
        blocks = streets.setdefault(loc.street_name, {})
        key = (loc.from_cross_street, loc.to_cross_street)
        blocks.setdefault(key, []).append(
            SideOption(side=loc.side, location_id=loc.location_id)
        )

    return LocationsResponse(
        generated=summary["generated"],
        source=summary["source"],
        neighborhoods=[
            NeighborhoodOption(
                name=nb,
                streets=[
                    StreetOption(
                        street_name=st,
                        blocks=[
                            BlockOption(
                                from_cross_street=frm,
                                to_cross_street=to,
                                sides=sorted(sides, key=lambda s: s.side),
                            )
                            for (frm, to), sides in blocks.items()
                        ],
                    )
                    for st, blocks in sorted(streets.items())
                ],
            )
            for nb, streets in sorted(tree.items())
        ],
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
        run_id=result.run_id,
        model=result.model,
        duration_ms=result.duration_ms,
        trace=trace,
    )


@app.post("/api/parking/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    if resolve_claude_cli() is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "The runtime agent is unavailable: the Claude Code CLI "
                "(subscription auth) was not found in this environment. See "
                "docs/deployment.md."
            ),
        )
    try:
        request = ParkingRequest(
            location_id=payload.location_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
            permit_zone=payload.permit_zone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        result = await run_parking_agent(request)
    except AgentAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _to_response(result)
