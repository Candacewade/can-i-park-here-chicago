"""``find_legal_parking_nearby`` -- deterministic alternative-parking search.

The agent decides *when* to call this (e.g. the user asks "where do I move?")
and how to present the options. It does not judge the individual results: each
candidate block is run through the same deterministic core pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import NEARBY_MAX_RESULTS, NEARBY_RADIUS_KM
from app.geo import approx_walk_minutes, haversine_km
from app.locations.registry import LocationNotFoundError, get_location, list_locations
from app.models.decision import ParkingStatus
from app.models.requests import ParkingRequest
from app.rules.engine import evaluate_parking
from app.rules.gather import gather_evidence

_OK = {ParkingStatus.LEGAL, ParkingStatus.LEGAL_UNTIL}


@dataclass
class NearbyOption:
    location_id: str
    summary: str
    distance_km: float
    walk_minutes: int
    status: str
    move_by_display: str | None


def find_legal_parking_nearby(
    location_id: str,
    start_time,
    end_time,
    permit_zone: str | None = None,
    *,
    radius_km: float = NEARBY_RADIUS_KM,
    max_results: int = NEARBY_MAX_RESULTS,
) -> list[NearbyOption]:
    try:
        origin = get_location(location_id)
    except LocationNotFoundError:
        return []
    if origin.latitude is None or origin.longitude is None:
        return []

    candidates: list[tuple[float, object]] = []
    for loc in list_locations():
        if loc.location_id == location_id or loc.latitude is None or loc.longitude is None:
            continue
        km = haversine_km(origin.latitude, origin.longitude, loc.latitude, loc.longitude)
        if km <= radius_km:
            candidates.append((km, loc))
    candidates.sort(key=lambda t: t[0])

    out: list[NearbyOption] = []
    for km, loc in candidates:
        request = ParkingRequest(
            location_id=loc.location_id,
            start_time=start_time,
            end_time=end_time,
            permit_zone=permit_zone,
        )
        decision = evaluate_parking(request, gather_evidence(request))
        if decision.status not in _OK:
            continue
        out.append(
            NearbyOption(
                location_id=loc.location_id,
                summary=loc.human_summary(),
                distance_km=round(km, 2),
                walk_minutes=approx_walk_minutes(km),
                status=decision.status.value,
                move_by_display=decision.move_by_display,
            )
        )
        if len(out) >= max_results:
            break
    return out
