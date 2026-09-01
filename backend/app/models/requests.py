"""The canonical parking request.

The frontend forces the user to *select* a location, side, interval, and permit
status. That selection collapses to a single ``location_id`` plus a time window.
The agent and rule engine only ever see this typed object -- never free text.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import CHICAGO_TZ

_PERMIT_ZONE_RE = re.compile(r"^\d{1,5}[A-Z]?$")


class ParkingRequest(BaseModel):
    """A fully-specified 'can I park here?' question.

    ``location_id`` must resolve against the location registry (validated later,
    where the registry is available -- keeping this model registry-free keeps it
    cheap to construct in tests).
    """

    location_id: str = Field(min_length=1, description="Canonical block+side id from the registry.")
    start_time: datetime = Field(description="Start of the desired parking interval.")
    end_time: datetime = Field(description="End of the desired parking interval.")
    permit_zone: str | None = Field(
        default=None,
        description="Residential permit zone the user holds, e.g. '143'. None = no permit.",
    )

    @field_validator("permit_zone")
    @classmethod
    def _check_permit_zone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        if v in {"", "NONE", "NULL", "N/A"}:
            return None
        if not _PERMIT_ZONE_RE.match(v):
            raise ValueError(f"permit_zone {v!r} is not a valid Chicago zone format")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def _require_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            # Interpret a naive datetime as Chicago local time rather than rejecting it.
            return v.replace(tzinfo=CHICAGO_TZ)
        return v

    @model_validator(mode="after")
    def _check_interval(self) -> ParkingRequest:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self
