"""Plain-function implementations behind the MCP tools.

Kept separate from ``server.py`` so they are directly unit-testable without an
MCP session.

Since the 2026-09-01 revision the deterministic core (residential, street
cleaning, temporary closures, winter snow route) is gathered by ``rules.gather``
inside ``evaluate_parking_request`` on every call -- there are no agent tools for
it. These handlers are the agent's *investigation* surface: weather, snow-route
membership, nearby events, closure detail, and alternative parking. Investigation
tools persist their output in ``evidence_store`` under the run's run_id;
``evaluate_parking_request`` merges the verdict-relevant ones and re-evaluates.
"""

from __future__ import annotations

from datetime import datetime

from app import evidence_store
from app.config import CHICAGO_TZ
from app.locations.registry import LocationNotFoundError, get_location, list_locations
from app.models.requests import ParkingRequest
from app.rules.completeness import check_completeness
from app.rules.engine import evaluate_parking
from app.rules.gather import gather_evidence
from app.rules.nearby import find_legal_parking_nearby
from app.services.events import get_nearby_events
from app.services.snow_routes import get_snow_route_evidence
from app.services.street_closures import get_street_closure_evidence
from app.services.weather import get_weather_outlook as _weather_svc

_NULLISH = {"", "none", "null", "n/a"}


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CHICAGO_TZ)
    return dt


def _clean_permit(permit_zone: str | None) -> str | None:
    return None if (permit_zone or "").strip().lower() in _NULLISH else permit_zone


# --- context ---------------------------------------------------------

def get_location_context(location_id: str) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"found": False, "error": str(exc)}
    return {"found": True, "location": loc.model_dump(mode="json"), "summary": loc.human_summary()}


def list_supported_locations() -> dict:
    return {
        "locations": [
            {"location_id": loc.location_id, "summary": loc.human_summary()}
            for loc in list_locations()
        ]
    }


# --- investigation (store + return) ---------------------------------

def get_weather_outlook(
    run_id: str, location_id: str, start_time: str, end_time: str
) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"status": "UNSUPPORTED", "error": str(exc)}
    try:
        start, end = _parse_dt(start_time), _parse_dt(end_time)
    except ValueError as exc:
        return {"status": "UNAVAILABLE", "error": f"bad datetime: {exc}"}
    evidence = _weather_svc(loc.latitude, loc.longitude, start, end)
    evidence_store.record(
        run_id, evidence_store.WEATHER,
        location_id=location_id, evidence=evidence, start=start, end=end,
    )
    return evidence.model_dump(mode="json")


def get_snow_route_status(
    run_id: str, location_id: str, start_time: str, end_time: str
) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"status": "UNSUPPORTED", "error": str(exc)}
    try:
        start, end = _parse_dt(start_time), _parse_dt(end_time)
    except ValueError as exc:
        return {"status": "UNAVAILABLE", "error": f"bad datetime: {exc}"}
    evidence = get_snow_route_evidence(loc, start, end)
    evidence_store.record(
        run_id, evidence_store.SNOW_ROUTE,
        location_id=location_id, evidence=evidence, start=start, end=end,
    )
    return evidence.model_dump(mode="json")


def get_nearby_events_tool(
    run_id: str, location_id: str, start_time: str, end_time: str
) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"status": "UNSUPPORTED", "error": str(exc)}
    try:
        start, end = _parse_dt(start_time), _parse_dt(end_time)
    except ValueError as exc:
        return {"status": "UNAVAILABLE", "error": f"bad datetime: {exc}"}
    evidence = get_nearby_events(loc, start, end)
    evidence_store.record(
        run_id, evidence_store.EVENTS,
        location_id=location_id, evidence=evidence, start=start, end=end,
    )
    return evidence.model_dump(mode="json")


def get_closure_detail(
    run_id: str, location_id: str, start_time: str, end_time: str
) -> dict:
    """Every public-way permit on the block (all work types), for explaining an
    unusual result. Not verdict-relevant (the core already handles parking-impact
    closures); stored for tracing only."""
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"status": "UNSUPPORTED", "error": str(exc)}
    try:
        start, end = _parse_dt(start_time), _parse_dt(end_time)
    except ValueError as exc:
        return {"status": "UNAVAILABLE", "error": f"bad datetime: {exc}"}
    evidence = get_street_closure_evidence(loc, start, end)
    evidence_store.record(
        run_id, evidence_store.CLOSURE_DETAIL,
        location_id=location_id, evidence=evidence, start=start, end=end,
    )
    return evidence.model_dump(mode="json")


def find_legal_parking_nearby_tool(
    run_id: str,
    location_id: str,
    start_time: str,
    end_time: str,
    permit_zone: str | None = None,
) -> dict:
    try:
        start, end = _parse_dt(start_time), _parse_dt(end_time)
    except ValueError as exc:
        return {"error": f"bad datetime: {exc}", "options": []}
    options = find_legal_parking_nearby(
        location_id, start, end, _clean_permit(permit_zone)
    )
    return {"options": [o.__dict__ for o in options]}


# --- the deterministic verdict -------------------------------------

def evaluate_parking_request(
    run_id: str,
    location_id: str,
    start_time: str,
    end_time: str,
    permit_zone: str | None = None,
) -> dict:
    try:
        request = ParkingRequest(
            location_id=location_id,
            start_time=_parse_dt(start_time),
            end_time=_parse_dt(end_time),
            permit_zone=_clean_permit(permit_zone),
        )
    except ValueError as exc:
        return {"decision": {"status": "UNKNOWN"}, "error": f"invalid request: {exc}"}

    evidence = gather_evidence(request)  # deterministic core, ALWAYS

    optional = evidence_store.verdict_relevant_evidence(
        run_id,
        location_id=request.location_id,
        start=request.start_time,
        end=request.end_time,
    )
    if evidence_store.WEATHER in optional:
        evidence.weather = optional[evidence_store.WEATHER]
    if evidence_store.EVENTS in optional:
        evidence.events = optional[evidence_store.EVENTS]
    if evidence.snow_route is None and evidence_store.SNOW_ROUTE in optional:
        evidence.snow_route = optional[evidence_store.SNOW_ROUTE]

    decision = evaluate_parking(request, evidence)
    completeness = check_completeness(request, evidence)
    return {
        "run_id": run_id,
        "decision": decision.model_dump(mode="json"),
        "completeness": {"complete": completeness.complete, "missing": completeness.missing},
        "evidence": evidence.model_dump(mode="json"),
    }
