"""Typed models: the canonical request, normalized evidence, and the decision."""

from app.models.decision import DecisionReason, ParkingDecision, ParkingStatus
from app.models.evidence import (
    EvidenceStatus,
    ParkingEvidence,
    ResidentialZoneEvidence,
    SourceProvenance,
    StreetCleaningEvidence,
    StreetCleaningWindow,
    TemporaryClosure,
    TemporaryClosureEvidence,
)
from app.models.requests import ParkingRequest

__all__ = [
    "DecisionReason",
    "EvidenceStatus",
    "ParkingDecision",
    "ParkingEvidence",
    "ParkingRequest",
    "ParkingStatus",
    "ResidentialZoneEvidence",
    "SourceProvenance",
    "StreetCleaningEvidence",
    "StreetCleaningWindow",
    "TemporaryClosure",
    "TemporaryClosureEvidence",
]
