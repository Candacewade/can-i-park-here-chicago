"""Independently gather every piece of parking evidence for a request.

The MCP ``evaluate_parking`` tool calls this -- it does NOT trust evidence
relayed by the agent. The agent's own restriction-tool calls are for its
understanding and explanation; the verdict is computed from a fresh, deterministic
gather. (The short cache in ``services.socrata`` means this rarely costs extra
HTTP round trips.)
"""

from __future__ import annotations

from app.locations.registry import LocationNotFoundError, get_location
from app.models.evidence import EvidenceStatus, ParkingEvidence, ResidentialZoneEvidence
from app.models.requests import ParkingRequest
from app.services.residential_zones import get_residential_zone_evidence
from app.services.street_cleaning import get_street_cleaning_evidence
from app.services.street_closures import get_street_closure_evidence


def gather_evidence(request: ParkingRequest) -> ParkingEvidence:
    try:
        location = get_location(request.location_id)
    except LocationNotFoundError as exc:
        unsupported = ResidentialZoneEvidence(
            status=EvidenceStatus.UNSUPPORTED, notes=[str(exc)]
        )
        return ParkingEvidence(residential=unsupported)

    return ParkingEvidence(
        residential=get_residential_zone_evidence(location),
        street_cleaning=get_street_cleaning_evidence(
            location, request.start_time, request.end_time
        ),
        temporary_closure=get_street_closure_evidence(
            location, request.start_time, request.end_time
        ),
    )
