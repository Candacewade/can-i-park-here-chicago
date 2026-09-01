"""The Chicago-parking MCP server (stdio transport).

Run directly for the agent to spawn:  python -m app.mcp.server

Exposes a fixed toolbox. Every tool:
  * does one clear thing
  * takes a canonical ``location_id`` (never a free-text address)
  * returns typed, normalized evidence as JSON
  * turns any data-source failure into an explicit UNAVAILABLE status
It deliberately exposes no generic HTTP, filesystem, or shell capability.
"""

from __future__ import annotations

from datetime import datetime

from mcp.server.mcpserver import MCPServer

from app.locations.registry import (
    LocationNotFoundError,
    get_location,
    list_locations,
)
from app.services.residential_zones import get_residential_zone_evidence
from app.services.street_cleaning import get_street_cleaning_evidence

mcp = MCPServer(
    name="chicago-parking",
    version="0.1.0",
    instructions=(
        "Authoritative Chicago parking evidence. Call get_location_context first to "
        "confirm the block, then the restriction tools you need. Never treat an "
        "UNAVAILABLE result as 'no restriction'."
    ),
)


@mcp.tool(
    description=(
        "Resolve a canonical location_id to its Chicago block: street, cross "
        "streets, side, neighborhood, address range, and the ward/section used "
        "for street cleaning. Call this first to confirm you have the right block. "
        "If the id is unknown, the location is outside supported Chicago coverage."
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
        "Residential permit-parking status for the block+side of this location_id, "
        "from the City of Chicago 'Permit Parking Zones' dataset. Returns the permit "
        "zone required to park here (or null if the block is not in a residential "
        "zone), whether it is a buffer segment, and a VERIFIED / UNAVAILABLE status. "
        "Use when the request involves overnight or daytime on-street parking in a "
        "residential area, or whenever a permit_zone was supplied."
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
        "Scheduled street-cleaning (street sweeping) windows for this location_id "
        "that overlap the given parking interval, from the City of Chicago 2026 "
        "Street Sweeping Schedule. Returns each cleaning window (date, assumed "
        "09:00-15:00 hours) plus a VERIFIED / UNAVAILABLE / UNSUPPORTED status. "
        "start_time and end_time are ISO-8601 with timezone offset. Always call "
        "this for any overnight or multi-day parking request."
    )
)
def get_street_cleaning_restrictions(
    location_id: str, start_time: str, end_time: str
) -> dict:
    try:
        loc = get_location(location_id)
    except LocationNotFoundError as exc:
        return {"status": "UNSUPPORTED", "error": str(exc)}
    try:
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
    except ValueError as exc:
        return {"status": "UNAVAILABLE", "error": f"bad datetime: {exc}"}
    return get_street_cleaning_evidence(loc, start, end).model_dump(mode="json")


@mcp.tool(
    description=(
        "List every canonical location_id currently supported, with a short human "
        "description. Use only if you need to discover valid ids; normally the "
        "location_id is supplied in the request."
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
