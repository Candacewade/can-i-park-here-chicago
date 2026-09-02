"""Request/response models for the HTTP API.

These are deliberately separate from the internal domain models so the wire
contract can evolve independently.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.decision import DecisionReason, ParkingStatus

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# --- POST /api/locations/resolve  (Slice 5) --------------------------

class ResolveRequest(BaseModel):
    number: int = Field(gt=0, description="Street number, e.g. 2400")
    street: str = Field(min_length=1, description="e.g. 'N Clark St'")
    zip_code: str = Field(default="", description="Chicago ZIP; optional but improves the match")
    side: str | None = Field(
        default=None, description="Set when re-resolving with a confirmed side"
    )


class SideCandidate(BaseModel):
    side: str
    location_id: str
    summary: str


class ResolveResponse(BaseModel):
    in_chicago: bool
    matched_address: str | None = None
    street_name: str | None = None
    neighborhood: str | None = None
    from_cross_street: str | None = None
    to_cross_street: str | None = None
    street_sweeping_ward: str | None = None
    street_sweeping_section: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    suggested_side: str | None = None
    side_confidence: str = "low"          # user | high | low
    side_options: list[SideCandidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ExampleAddress(BaseModel):
    label: str
    number: int
    street: str
    zip_code: str


# --- POST /api/parking/analyze ---------------------------------------

class AnalyzeRequest(BaseModel):
    location_id: str = Field(min_length=1)
    # Naive local datetimes are accepted and interpreted as America/Chicago.
    start_time: datetime
    end_time: datetime
    permit_zone: str | None = None


class ToolCallView(BaseModel):
    order: int
    name: str
    status: str  # "ok" | "error"
    latency_ms: float | None = None
    arguments: dict
    result_preview: str


class AnalyzeResponse(BaseModel):
    status: ParkingStatus
    move_by: datetime | None = None
    start_time_display: str | None = None
    end_time_display: str | None = None
    move_by_display: str | None = None

    urgent_alert: bool = False
    urgent_reason: str | None = None

    summary: str = Field(description="The agent's grounded plain-language explanation.")
    reasons: list[DecisionReason] = Field(default_factory=list)
    unknown_reasons: list[str] = Field(default_factory=list)
    completeness_complete: bool = True

    # The deterministic verdict *before* the agent investigated -- lets the UI
    # show when investigation changed the answer.
    core_status: ParkingStatus | None = None

    # False -> the Claude runtime was unavailable; `summary` is a deterministic
    # template and `trace` is empty. The verdict itself is unaffected.
    agent_available: bool = True

    # Developer / educational view (Master Build Plan sec. 19, 42).
    run_id: str
    model: str
    duration_ms: float | None = None
    trace: list[ToolCallView] = Field(default_factory=list)


# --- watches (Slice 4) ------------------------------------------------

class CreateWatchRequest(BaseModel):
    location_id: str = Field(min_length=1)
    start_time: datetime
    end_time: datetime
    permit_zone: str | None = None
    email: str = Field(
        description="Notification address. Stored only in the secret map, never in the repo."
    )

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("not a valid email address")
        return v


class CreateWatchResponse(BaseModel):
    watch_id: str
    # Opaque per-watch capability token. The frontend keeps this (localStorage)
    # to later stop or move the watch; it is also embedded in that watch's
    # own email management links. Not PII.
    manage_token: str
    email_registered: bool
    note: str


class ReplaceWatchRequest(BaseModel):
    """Move the monitored spot: resolve the old watch, create a new one. Atomic."""

    token: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    start_time: datetime
    end_time: datetime
    permit_zone: str | None = None
    # Optional: reuse the recipient already on file for the old watch when omitted.
    email: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("not a valid email address")
        return v


class ReplaceWatchResponse(BaseModel):
    old_watch_id: str
    watch_id: str
    manage_token: str
    email_registered: bool


class ExtendWatchRequest(BaseModel):
    """Keep the same spot / side / email / start / permit / watch identity -- only
    push the end of the parking window later."""

    token: str = Field(min_length=1)
    end_time: datetime


class ExtendWatchResponse(BaseModel):
    watch_id: str
    manage_token: str            # unchanged; echoed so the client keeps its copy
    end_time: datetime
    end_time_local: str          # "YYYY-MM-DDTHH:MM" America/Chicago wall time
    through_display: str
    # deterministic re-evaluation of the *extended* interval
    status: ParkingStatus
    start_time_display: str | None = None
    end_time_display: str | None = None
    move_by_display: str | None = None
    urgent_alert: bool = False
    summary: str


class WatchView(BaseModel):
    """No email is ever echoed back."""

    watch_id: str
    location_id: str
    start_time: datetime
    end_time: datetime
    permit_zone: str | None
    status: str
    created_at: datetime
    last_decision: str | None
    last_checked_at: datetime | None
    notified_count: int
    # Display helpers so a client with only {watch_id, token} (e.g. an email
    # "change parking spot" link on a fresh device) can render the monitor card.
    location_summary: str | None = None
    through_display: str | None = None
    end_time_local: str | None = None   # "YYYY-MM-DDTHH:MM" -- prefill the extend form


class MonitorRunResponse(BaseModel):
    ran_at: datetime
    checked: int
    emails_sent: int
    summary: str
