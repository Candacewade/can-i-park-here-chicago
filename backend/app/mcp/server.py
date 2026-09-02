"""The Chicago-parking MCP server (stdio transport).

Run directly for the agent to spawn:  python -m app.mcp.server

Exposes a fixed toolbox. Every tool does one clear thing, takes a canonical
``location_id`` (never a free-text address), and returns typed JSON. Any
data-source failure becomes an explicit UNAVAILABLE / UNSUPPORTED status.
No generic HTTP, filesystem, or shell capability is exposed.

Orchestration model:
  * every tool takes a ``run_id``; the evidence tools store their authoritative
    normalized output server-side under that run_id (see app.evidence_store).
  * ``evaluate_parking_request`` reads those stored outputs -- it does not
    re-fetch and does not trust anything the agent relays.
  * the deterministic completeness check then requires that every safety
    category was actually gathered and VERIFIED, else the verdict is UNKNOWN.

The descriptions say what each tool answers and when it is relevant; they do not
script a call order. The agent chooses which evidence to gather.

Implementations live in app.mcp.handlers (unit-testable without a session).
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from app.mcp import handlers

mcp = MCPServer(
    name="chicago-parking",
    version="0.3.0",
    instructions=(
        "Authoritative Chicago parking evidence and the deterministic evaluator. "
        "Pass the request's run_id to every tool. Gather the evidence the request "
        "needs, then call evaluate_parking_request for the official decision. An "
        "UNAVAILABLE or UNSUPPORTED result never means 'no restriction'."
    ),
)


@mcp.tool(
    description=(
        "Resolve a canonical location_id to its Chicago block: street, cross "
        "streets, side, neighborhood, address range, and the ward/section used for "
        "street cleaning. Use it to confirm you have the right block. An unknown "
        "id means the location is outside supported Chicago coverage."
    )
)
def get_location_context(location_id: str) -> dict:
    return handlers.get_location_context(location_id)


@mcp.tool(
    description=(
        "Residential permit-parking status for this block+side, from the City of "
        "Chicago 'Permit Parking Zones' dataset. Returns the permit zone required "
        "to park here (null if the block is not in a residential zone), whether it "
        "is a buffer segment, and a VERIFIED / UNAVAILABLE / UNSUPPORTED status. "
        "Relevant when the block might be in a residential zone or when the request "
        "carries a permit_zone. Pass the request's run_id."
    )
)
def get_residential_restrictions(run_id: str, location_id: str) -> dict:
    return handlers.get_residential_restrictions(run_id, location_id)


@mcp.tool(
    description=(
        "Scheduled street-cleaning (street sweeping) windows for this block that "
        "overlap the given interval, from the City of Chicago 2026 Street Sweeping "
        "Schedule. Returns each window (date; hours assumed 09:00-15:00) plus a "
        "VERIFIED / UNAVAILABLE / UNSUPPORTED status. Times are ISO-8601 with "
        "offset. Relevant whenever the interval could reach a daytime hour on a "
        "day the block is swept. Pass the request's run_id."
    )
)
def get_street_cleaning_restrictions(
    run_id: str, location_id: str, start_time: str, end_time: str
) -> dict:
    return handlers.get_street_cleaning_restrictions(run_id, location_id, start_time, end_time)


@mcp.tool(
    description=(
        "Temporary street-closure and public-way permits (construction, work "
        "zones, utility openings, block parties) that would remove on-street "
        "parking on this block during the interval, from the City of Chicago "
        "transportation-permits dataset. Returns each overlapping permit plus a "
        "VERIFIED / UNAVAILABLE status. Useful for ruling out a short-notice "
        "closure the recurring schedules would not show. Pass the request's run_id."
    )
)
def get_temporary_closures(
    run_id: str, location_id: str, start_time: str, end_time: str
) -> dict:
    return handlers.get_temporary_closures(run_id, location_id, start_time, end_time)


@mcp.tool(
    description=(
        "The official deterministic parking decision for this request. It reads "
        "the evidence that the other tools stored for this run_id (it does not "
        "re-fetch and does not accept evidence from you), runs a completeness "
        "check, and returns a ParkingDecision: status LEGAL / NOT_LEGAL / "
        "LEGAL_UNTIL / UNKNOWN, an optional move_by, the reasons, any unverified "
        "categories, and start_time_display / end_time_display / move_by_display "
        "(America/Chicago). If a required evidence tool was not run for this "
        "run_id, that category is missing and the status is UNKNOWN. Call this "
        "once you have gathered what the request needs. permit_zone is optional; "
        "times are ISO-8601 with offset. Pass the request's run_id."
    )
)
def evaluate_parking_request(
    run_id: str,
    location_id: str,
    start_time: str,
    end_time: str,
    permit_zone: str | None = None,
) -> dict:
    return handlers.evaluate_parking_request(
        run_id, location_id, start_time, end_time, permit_zone
    )


@mcp.tool(
    description=(
        "List every canonical location_id currently supported, with a short human "
        "description. Use only to discover valid ids; normally the location_id is "
        "supplied in the request."
    )
)
def list_supported_locations() -> dict:
    return handlers.list_supported_locations()


if __name__ == "__main__":
    mcp.run("stdio")
