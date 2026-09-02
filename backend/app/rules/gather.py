"""Independently gather every piece of parking evidence for a request in one call.

NOT on the agent path. In production the agent calls the individual MCP evidence
tools (which store their output in ``app.evidence_store``) and then
``evaluate_parking_request`` reads that stored evidence. This helper is the
non-agent equivalent: it is used by tests and by any future deterministic-only
baseline (e.g. an eval harness that scores the agent against a full gather).
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
