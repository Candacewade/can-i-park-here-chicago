"""Deterministic evidence-completeness check.

A verdict of LEGAL / NOT_LEGAL / LEGAL_UNTIL is only allowed if every
safety-required evidence category was actually VERIFIED. A required category
that is missing, UNAVAILABLE, or UNSUPPORTED forces UNKNOWN (unless a verified
restriction already makes the answer NOT_LEGAL -- that precedence is in
``engine.py``).

Since the 2026-09-01 revision the required set is season-aware and the core
categories are always gathered, so "missing" really only happens on a data-source
failure or an unsupported location.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.evidence import EvidenceStatus, ParkingEvidence
from app.models.requests import ParkingRequest
from app.services.snow_routes import in_overnight_ban_period

_ALWAYS_REQUIRED = ("residential", "street_cleaning", "temporary_closure")


def required_categories(request: ParkingRequest) -> tuple[str, ...]:
    """Which evidence categories must be VERIFIED for this request."""
    required = list(_ALWAYS_REQUIRED)
    if in_overnight_ban_period(request.start_time) or in_overnight_ban_period(request.end_time):
        required.append("snow_route")
    return tuple(required)


@dataclass
class CompletenessResult:
    complete: bool
    missing: list[str] = field(default_factory=list)  # human-readable "category: why"


def check_completeness(request: ParkingRequest, evidence: ParkingEvidence) -> CompletenessResult:
    missing: list[str] = []
    for category in required_categories(request):
        ev = getattr(evidence, category, None)
        if ev is None:
            missing.append(f"{category}: not gathered")
            continue
        if ev.status != EvidenceStatus.VERIFIED:
            detail = "; ".join(ev.notes) if getattr(ev, "notes", None) else "no detail"
            missing.append(f"{category}: {ev.status.value} ({detail})")
    return CompletenessResult(complete=not missing, missing=missing)
