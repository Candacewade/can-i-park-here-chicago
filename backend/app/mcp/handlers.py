"""Plain-function implementations behind the MCP tools.

Kept separate from ``server.py`` so they are directly unit-testable without an
MCP session. Each evidence handler:

  1. fetches authoritative data via a service client,
  2. records the normalized typed evidence in ``evidence_store`` under the
     caller's run_id, and
  3. returns the same evidence as JSON for the agent to read.

``evaluate_parking_request`` never re-fetches and never trusts agent-relayed
data: it reads the stored evidence for the run and hands it to the deterministic
rule engine.
"""

from __future__ import annotations

from datetime import datetime

from app import evidence_store
from app.config import CHICAGO_TZ
from app.locations.registry import LocationNotFoundError, get_location
from app.models.requests import ParkingRequest
from app.rules.completeness import check_completeness
from app.rules.engine import evaluate_parking
from app.services.residential_zones import get_residential_zone_evidence
from app.services.street_cleaning import get_street_cleaning_evidence
from app.services.street_closures import get_street_closure_evidence

_NULLISH = {"", "none", "null", "n/a"}


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CHICAGO_TZ)
    return dt


def get_location_context(location_id: str) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"found": False, "error": str(exc)}
    return {"found": True, "location": loc.model_dump(mode="json"), "summary": loc.human_summary()}


def list_supported_locations() -> dict:
    from app.locations.registry import list_locations

    return {
        "locations": [
            {"location_id": loc.location_id, "summary": loc.human_summary()}
            for loc in list_locations()
        ]
    }


def get_residential_restrictions(run_id: str, location_id: str) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"status": "UNSUPPORTED", "error": str(exc)}
    evidence = get_residential_zone_evidence(loc)
    evidence_store.record(
        run_id, evidence_store.RESIDENTIAL, location_id=location_id, evidence=evidence
    )
    return evidence.model_dump(mode="json")


def get_street_cleaning_restrictions(
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
    evidence = get_street_cleaning_evidence(loc, start, end)
    evidence_store.record(
        run_id, evidence_store.STREET_CLEANING,
        location_id=location_id, evidence=evidence, start=start, end=end,
    )
    return evidence.model_dump(mode="json")


def get_temporary_closures(
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
    evidence = get_street_closure_evidence(loc, start, end)
    evidence_store.record(
        run_id, evidence_store.TEMPORARY_CLOSURE,
        location_id=location_id, evidence=evidence, start=start, end=end,
    )
    return evidence.model_dump(mode="json")


def evaluate_parking_request(
    run_id: str,
    location_id: str,
    start_time: str,
    end_time: str,
    permit_zone: str | None = None,
) -> dict:
    if (permit_zone or "").strip().lower() in _NULLISH:
        permit_zone = None
    try:
        request = ParkingRequest(
            location_id=location_id,
            start_time=_parse_dt(start_time),
            end_time=_parse_dt(end_time),
            permit_zone=permit_zone,
        )
    except ValueError as exc:
        return {"decision": {"status": "UNKNOWN"}, "error": f"invalid request: {exc}"}

    evidence = evidence_store.build_bundle(
        run_id,
        location_id=request.location_id,
        start=request.start_time,
        end=request.end_time,
    )
    decision = evaluate_parking(request, evidence)
    completeness = check_completeness(request, evidence)
    return {
        "run_id": run_id,
        "decision": decision.model_dump(mode="json"),
        "completeness": {"complete": completeness.complete, "missing": completeness.missing},
        "evidence": evidence.model_dump(mode="json"),
    }
