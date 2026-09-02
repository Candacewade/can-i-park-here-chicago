"""The parking decision -- produced only by the deterministic rule engine.

The LLM never constructs one of these. It receives a finished ParkingDecision and
explains it.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ParkingStatus(StrEnum):
    LEGAL = "LEGAL"
    NOT_LEGAL = "NOT_LEGAL"
    LEGAL_UNTIL = "LEGAL_UNTIL"
    UNKNOWN = "UNKNOWN"


class DecisionReason(BaseModel):
    """One concrete, evidence-backed factor in the decision."""

    category: str = Field(description="e.g. 'residential', 'street_cleaning'.")
    verdict: str = Field(description="'allows', 'blocks', 'limits', or 'unknown'.")
    detail: str
    source_dataset_id: str | None = None


class ParkingDecision(BaseModel):
    status: ParkingStatus
    move_by: datetime | None = Field(
        default=None, description="For LEGAL_UNTIL: when the user must have left."
    )
    reasons: list[DecisionReason] = Field(default_factory=list)
    unknown_reasons: list[str] = Field(
        default_factory=list, description="Why we could not fully verify (drives UNKNOWN)."
    )

    # Deterministically formatted America/Chicago strings. The agent restates
    # these verbatim -- it must never compute a weekday or convert a time itself.
    start_time_display: str | None = None
    end_time_display: str | None = None
    move_by_display: str | None = None

    # Hard urgent-alert trigger. Set deterministically: a verified restriction
    # requires the car to move within the urgent window. The agent may prioritize
    # and word the alert; it may NOT decide whether this fires.
    urgent_alert: bool = False
    urgent_reason: str | None = None
