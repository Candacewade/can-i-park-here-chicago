"""The Chicago-parking MCP server (stdio transport).

Run directly for the agent to spawn:  python -m app.mcp.server

Exposes a fixed toolbox. Every tool:
  * does one clear thing
  * takes a canonical ``location_id`` (never a free-text address)
  * returns typed, normalized evidence as JSON
  * turns any data-source failure into an explicit UNAVAILABLE status
It deliberately exposes no generic HTTP, filesystem, or shell capability.

The descriptions say what each tool answers and when it is relevant, but do not
script an order -- the agent chooses. ``evaluate_parking`` re-gathers evidence
independently and runs a deterministic completeness check, so a skipped check
cannot turn into a false "you can park".
"""

from __future__ import annotations

from datetime import datetime

from mcp.server.mcpserver import MCPServer

from app.locations.registry import LocationNotFoundError, get_location, list_locations
from app.models.requests import ParkingRequest
from app.rules.completeness import check_completeness
from app.rules.engine import evaluate_parking
from app.rules.gather import gather_evidence
from app.services.residential_zones import get_residential_zone_evidence
from app.services.street_cleaning import get_street_cleaning_evidence
from app.services.street_closures import get_street_closure_evidence

mcp = MCPServer(
    name="chicago-parking",
    version="0.2.0",
    instructions=(
        "Authoritative Chicago parking evidence and the deterministic parking "
        "evaluator. Gather the evidence the request needs, then call "
        "evaluate_parking for the official decision. An UNAVAILABLE or UNSUPPORTED "
        "result never means 'no restriction'."
    ),
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


@mcp.tool(
    description=(
        "Resolve a canonical location_id to its Chicago block: street, cross "
        "streets, side, neighborhood, address range, and the ward/section used for "
        "street cleaning. Use it to confirm you have the right block before "
        "reasoning about restrictions. An unknown id means the location is outside "
        "supported Chicago coverage."
    )
)
def get_location_context(location_id: str) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"found": False, "error": str(exc)}
    return {"found": True, "location": loc.model_dump(mode="json"), "summary": loc.human_summary()}


@mcp.tool(
    description=(
        "Residential permit-parking status for this block+side, from the City of "
        "Chicago 'Permit Parking Zones' dataset. Returns the permit zone required "
        "to park here (null if the block is not in a residential zone), whether it "
        "is a buffer segment, and a VERIFIED / UNAVAILABLE / UNSUPPORTED status. "
        "Relevant when the block might be in a residential zone or when the request "
        "carries a permit_zone to check."
    )
)
def get_residential_restrictions(location_id: str) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"status": "UNSUPPORTED", "error": str(exc)}
    return get_residential_zone_evidence(loc).model_dump(mode="json")


@mcp.tool(
    description=(
        "Scheduled street-cleaning (street sweeping) windows for this block that "
        "overlap the given interval, from the City of Chicago 2026 Street Sweeping "
        "Schedule. Returns each window (date; hours assumed 09:00-15:00) plus a "
        "VERIFIED / UNAVAILABLE / UNSUPPORTED status. start_time/end_time are "
        "ISO-8601 with offset. Relevant whenever the interval could reach a "
        "daytime hour on a day the block is swept -- e.g. overnight, early-morning, "
        "or multi-day parking."
    )
)
def get_street_cleaning_restrictions(location_id: str, start_time: str, end_time: str) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"status": "UNSUPPORTED", "error": str(exc)}
    try:
        start, end = _dt(start_time), _dt(end_time)
    except ValueError as exc:
        return {"status": "UNAVAILABLE", "error": f"bad datetime: {exc}"}
    return get_street_cleaning_evidence(loc, start, end).model_dump(mode="json")


@mcp.tool(
    description=(
        "Temporary street-closure and public-way permits (construction, work "
        "zones, utility openings, block parties) that would remove on-street "
        "parking on this block during the interval, from the City of Chicago "
        "transportation-permits dataset. Returns each overlapping permit (number, "
        "closure type, dates, meter-posting flag) plus a VERIFIED / UNAVAILABLE "
        "status. Useful for ruling out a short-notice closure that the recurring "
        "schedules would not show."
    )
)
def get_temporary_closures(location_id: str, start_time: str, end_time: str) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"status": "UNSUPPORTED", "error": str(exc)}
    try:
        start, end = _dt(start_time), _dt(end_time)
    except ValueError as exc:
        return {"status": "UNAVAILABLE", "error": f"bad datetime: {exc}"}
    return get_street_closure_evidence(loc, start, end).model_dump(mode="json")


@mcp.tool(
    description=(
        "The official deterministic parking decision for this request. It "
        "re-gathers every authoritative dataset itself (it does not use evidence "
        "you pass in), runs a completeness check, and returns a ParkingDecision: "
        "status LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN, an optional move_by "
        "time, the reasons, and any unverified categories. Call this once you have "
        "gathered what the request needs; you cannot compute or override this "
        "verdict yourself. permit_zone is optional. Times are ISO-8601 with offset."
    )
)
def evaluate_parking_request(
    location_id: str, start_time: str, end_time: str, permit_zone: str | None = None
) -> dict:
    if (permit_zone or "").strip().lower() in {"", "none", "null", "n/a"}:
        permit_zone = None
    try:
        request = ParkingRequest(
            location_id=location_id,
            start_time=_dt(start_time),
            end_time=_dt(end_time),
            permit_zone=permit_zone,
        )
    except ValueError as exc:
        return {"status": "UNKNOWN", "error": f"invalid request: {exc}"}

    evidence = gather_evidence(request)
    decision = evaluate_parking(request, evidence)
    completeness = check_completeness(request, evidence)
    return {
        "decision": decision.model_dump(mode="json"),
        "completeness": {"complete": completeness.complete, "missing": completeness.missing},
        "evidence": evidence.model_dump(mode="json"),
    }


@mcp.tool(
    description=(
        "List every canonical location_id currently supported, with a short human "
        "description. Use only to discover valid ids; normally the location_id is "
        "supplied in the request."
    )
)
def list_supported_locations() -> dict:
    return {
        "locations": [
            {"location_id": loc.location_id, "summary": loc.human_summary()}
            for loc in list_locations()
        ]
    }


if __name__ == "__main__":
    mcp.run("stdio")
