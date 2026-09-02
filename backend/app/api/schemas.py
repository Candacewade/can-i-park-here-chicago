"""Request/response models for the HTTP API.

These are deliberately separate from the internal domain models so the wire
contract can evolve independently.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.decision import DecisionReason, ParkingStatus

# --- GET /api/locations ------------------------------------------------

class SideOption(BaseModel):
    side: str
    location_id: str


class BlockOption(BaseModel):
    from_cross_street: str
    to_cross_street: str
    sides: list[SideOption]


class StreetOption(BaseModel):
    street_name: str
    blocks: list[BlockOption]


class NeighborhoodOption(BaseModel):
    name: str
    streets: list[StreetOption]


class LocationsResponse(BaseModel):
    generated: bool
    source: str
    neighborhoods: list[NeighborhoodOption]


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

    # Developer / educational view (Master Build Plan sec. 19, 42).
    run_id: str
    model: str
    duration_ms: float | None = None
    trace: list[ToolCallView] = Field(default_factory=list)
