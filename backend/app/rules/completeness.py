"""Deterministic evidence-completeness check.

This is the safety net that lets the agent genuinely *choose* which tools to
call: whatever it does, a verdict of LEGAL / NOT_LEGAL / LEGAL_UNTIL is only
allowed if every safety-required evidence category was actually VERIFIED. A
required category that is missing, UNAVAILABLE, or UNSUPPORTED forces UNKNOWN
(unless a different, verified restriction already makes the answer NOT_LEGAL --
that precedence lives in ``engine.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.evidence import EvidenceStatus, ParkingEvidence
from app.models.requests import ParkingRequest

# Categories that must be verified before we may tell someone they can park.
# Every one of these can independently produce a ticket in Chicago.
_ALWAYS_REQUIRED = ("residential", "street_cleaning", "temporary_closure")


def required_categories(request: ParkingRequest) -> tuple[str, ...]:
    """Which evidence categories must be VERIFIED for this request.

    Currently fixed. Kept as a function so future rules can make it depend on the
    request (e.g. add 'snow_route' only in winter, 'meter' only downtown).
    """
    return _ALWAYS_REQUIRED


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
