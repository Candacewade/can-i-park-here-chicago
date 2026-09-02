"""The deterministic core evidence gather -- runs on every request.

Since the 2026-09-01 revision this is *the* primary path (not a "non-agent
baseline"). Both the API/agent orchestration and any direct/eval path call it.
It always fetches the required categories; the agent can only *add* optional
evidence (weather, events, off-season snow) on top.
"""

from __future__ import annotations

from app.locations.registry import LocationNotFoundError, get_location
from app.models.evidence import EvidenceStatus, ParkingEvidence, ResidentialZoneEvidence
from app.models.requests import ParkingRequest
from app.services.residential_zones import get_residential_zone_evidence
from app.services.snow_routes import get_snow_route_evidence, in_overnight_ban_period
from app.services.street_cleaning import get_street_cleaning_evidence
from app.services.street_closures import get_street_closure_evidence


def _snow_is_core(request: ParkingRequest) -> bool:
    """Snow-route evidence is part of the required core when the interval touches
    the Dec 1 - Apr 1 overnight-ban season."""
    return in_overnight_ban_period(request.start_time) or in_overnight_ban_period(request.end_time)


def gather_evidence(request: ParkingRequest) -> ParkingEvidence:
    try:
        location = get_location(request.location_id)
    except LocationNotFoundError as exc:
        return ParkingEvidence(
            residential=ResidentialZoneEvidence(
                status=EvidenceStatus.UNSUPPORTED, notes=[str(exc)]
            )
        )

    evidence = ParkingEvidence(
        residential=get_residential_zone_evidence(location),
        street_cleaning=get_street_cleaning_evidence(
            location, request.start_time, request.end_time
        ),
        temporary_closure=get_street_closure_evidence(
            location, request.start_time, request.end_time
        ),
    )
    if _snow_is_core(request):
        evidence.snow_route = get_snow_route_evidence(
            location, request.start_time, request.end_time
        )
    return evidence
