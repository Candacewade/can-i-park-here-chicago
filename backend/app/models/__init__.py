"""Typed models: the canonical request, normalized evidence, and the decision."""

from app.models.decision import DecisionReason, ParkingDecision, ParkingStatus
from app.models.evidence import (
    EventImpactEvidence,
    EvidenceStatus,
    NearbyEvent,
    ParkingEvidence,
    ResidentialZoneEvidence,
    SnowRouteEvidence,
    SourceProvenance,
    StreetCleaningEvidence,
    StreetCleaningWindow,
    TemporaryClosure,
    TemporaryClosureEvidence,
    WeatherOutlookEvidence,
)
from app.models.requests import ParkingRequest

__all__ = [
    "DecisionReason",
    "EventImpactEvidence",
    "EvidenceStatus",
    "NearbyEvent",
    "ParkingDecision",
    "ParkingEvidence",
    "ParkingRequest",
    "ParkingStatus",
    "ResidentialZoneEvidence",
    "SnowRouteEvidence",
    "SourceProvenance",
    "StreetCleaningEvidence",
    "StreetCleaningWindow",
    "TemporaryClosure",
    "TemporaryClosureEvidence",
    "WeatherOutlookEvidence",
]
