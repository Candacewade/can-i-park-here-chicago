"""Developer CLI: run one ParkingRequest through the agent and print the trace.

    python -m app.cli --location wrightwood-3300w-north \\
        --start 2026-09-08T19:00:00-05:00 --end 2026-09-09T11:00:00-05:00 --permit 100

With no arguments it runs a built-in demo request.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta

from app.agent.parking_agent import format_trace, run_parking_agent
from app.config import CHICAGO_TZ
from app.locations.registry import list_locations
from app.models.requests import ParkingRequest


def _default_request() -> ParkingRequest:
    start = datetime.now(tz=CHICAGO_TZ).replace(hour=19, minute=0, second=0, microsecond=0)
    return ParkingRequest(
        location_id="wrightwood-3300w-north",
        start_time=start,
        end_time=start + timedelta(hours=16),
        permit_zone=None,
    )


def _parse_args() -> ParkingRequest:
    parser = argparse.ArgumentParser(description="Run the Chicago parking agent.")
    parser.add_argument("--location", help="canonical location_id")
    parser.add_argument("--start", help="ISO-8601 start time (with offset)")
    parser.add_argument("--end", help="ISO-8601 end time (with offset)")
    parser.add_argument("--permit", help="residential permit zone held, e.g. 100")
    parser.add_argument("--list", action="store_true", help="list supported locations and exit")
    args = parser.parse_args()

    if args.list:
        for loc in list_locations():
            print(f"{loc.location_id:28s} {loc.human_summary()}")
        raise SystemExit(0)

    if not (args.location and args.start and args.end):
        return _default_request()

    return ParkingRequest(
        location_id=args.location,
        start_time=datetime.fromisoformat(args.start),
        end_time=datetime.fromisoformat(args.end),
        permit_zone=args.permit,
    )


def main() -> None:
    request = _parse_args()
    print(f"Running parking agent for {request.location_id} ...\n")
    result = asyncio.run(run_parking_agent(request))
    print(format_trace(result))


if __name__ == "__main__":
    main()
