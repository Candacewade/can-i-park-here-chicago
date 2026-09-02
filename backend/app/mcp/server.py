"""The Chicago-parking MCP server (stdio transport).

Run directly for the agent to spawn:  python -m app.mcp.server

Since the 2026-09-01 revision the deterministic core (residential, street
cleaning, temporary closures, winter snow route) is gathered before the agent
runs and handed to it as context -- there are no agent tools for it. This
toolbox is the agent's **investigation + re-evaluation** surface.

Every tool takes the request's ``run_id``. Investigation tools persist their
output in ``app.evidence_store`` under it; ``evaluate_parking_request`` re-runs
the deterministic pipeline (core gather always + the merged optional evidence).

No generic HTTP, filesystem, or shell capability is exposed. Implementations live
in ``app.mcp.handlers``.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from app.mcp import handlers

mcp = MCPServer(
    name="chicago-parking",
    version="0.4.0",
    instructions=(
        "Investigate a Chicago parking situation. The deterministic decision and "
        "core evidence are already in your context. Use these tools only when the "
        "situation warrants extra digging (winter/snow, nearby events, an unusual "
        "closure, or the user asking where to move), then call "
        "evaluate_parking_request to fold in what you found. Pass the run_id to "
        "every tool. An UNAVAILABLE result never means 'no risk'."
    ),
)


@mcp.tool(
    description=(
        "Resolve a canonical location_id to its Chicago block (street, cross "
        "streets, side, neighborhood, coordinates). Use to confirm the block."
    )
)
def get_location_context(location_id: str) -> dict:
    return handlers.get_location_context(location_id)


@mcp.tool(
    description=(
        "US National Weather Service snow / precipitation outlook for this block "
        "over the interval: expected snowfall (inches) and max precip probability. "
        "A forecast, not a fact. Relevant when the interval is in winter or snow "
        "is plausible -- especially if the block is a 2-inch snow route. Times are "
        "ISO-8601 with offset. Pass the run_id."
    )
)
def get_weather_outlook(run_id: str, location_id: str, start_time: str, end_time: str) -> dict:
    return handlers.get_weather_outlook(run_id, location_id, start_time, end_time)


@mcp.tool(
    description=(
        "Whether this block is on a City of Chicago 2-inch snow route (parking "
        "banned once 2+ inches accumulate) and whether the interval is in the "
        "Dec 1 - Apr 1 overnight-ban season. Pair with get_weather_outlook to "
        "judge real risk. Pass the run_id."
    )
)
def get_snow_route_status(run_id: str, location_id: str, start_time: str, end_time: str) -> dict:
    return handlers.get_snow_route_status(run_id, location_id, start_time, end_time)


@mcp.tool(
    description=(
        "Permitted special events (festival, parade, athletic, filming, ...) near "
        "this block during the interval, from the City transportation-permits "
        "dataset. Context only -- crowds and congestion; events that actually "
        "close the street are already in the core decision. Pass the run_id."
    )
)
def get_nearby_events(run_id: str, location_id: str, start_time: str, end_time: str) -> dict:
    return handlers.get_nearby_events_tool(run_id, location_id, start_time, end_time)


@mcp.tool(
    description=(
        "Every public-way permit on this block during the interval, including "
        "non-parking work types, with full detail. Use to explain an unusual or "
        "severe temporary-closure result to the user. Pass the run_id."
    )
)
def get_closure_detail(run_id: str, location_id: str, start_time: str, end_time: str) -> dict:
    return handlers.get_closure_detail(run_id, location_id, start_time, end_time)


@mcp.tool(
    description=(
        "Deterministic: nearby supported blocks that evaluate to LEGAL or "
        "LEGAL_UNTIL for the same interval and permit, nearest first (distance + "
        "walk time). Call when the user asks where to move or when the decision "
        "is NOT_LEGAL / LEGAL_UNTIL and an alternative would help. permit_zone is "
        "optional. Pass the run_id."
    )
)
def find_legal_parking_nearby(
    run_id: str,
    location_id: str,
    start_time: str,
    end_time: str,
    permit_zone: str | None = None,
) -> dict:
    return handlers.find_legal_parking_nearby_tool(
        run_id, location_id, start_time, end_time, permit_zone
    )


@mcp.tool(
    description=(
        "The official deterministic parking decision. Re-runs the pipeline: the "
        "required core gather (always) + the verdict-relevant evidence your "
        "investigation tools stored for this run_id, then completeness + engine. "
        "Returns ParkingDecision (status LEGAL / NOT_LEGAL / LEGAL_UNTIL / "
        "UNKNOWN, move_by, start_time_display / end_time_display / "
        "move_by_display, urgent_alert, reasons, unknown_reasons). You cannot "
        "compute or override this. permit_zone optional; times ISO-8601 + offset. "
        "Pass the run_id."
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
        "List every canonical location_id currently supported. Use only to "
        "discover valid ids."
    )
)
def list_supported_locations() -> dict:
    return handlers.list_supported_locations()


if __name__ == "__main__":
    mcp.run("stdio")
