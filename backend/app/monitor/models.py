"""Watch model. Deliberately carries NO personally identifying information --
this object is serialized into watches.json in the private data repo."""

from __future__ import annotations

import secrets
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import CHICAGO_TZ
from app.models.decision import ParkingStatus


class WatchStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"   # the car was moved / the user cancelled
    EXPIRED = "expired"     # the planned end_time passed


class WatchOverride(BaseModel):
    """A self-reported correction to THIS watch's status -- e.g. a posted sign
    the user saw that the city dataset doesn't reflect. By explicit user
    choice this is a FULL override, either direction (docs/monitoring.md):
    while active it replaces the deterministic verdict for this watch's own
    emails/alerts. It never touches city data, the rule engine, or any other
    watch -- and it auto-expires (`expires_at`) rather than lingering."""

    status: ParkingStatus
    move_by: datetime | None = None
    note: str = Field(min_length=1, max_length=500)
    reported_at: datetime = Field(default_factory=lambda: datetime.now(tz=CHICAGO_TZ))
    expires_at: datetime

    @field_validator("move_by", "reported_at", "expires_at")
    @classmethod
    def _localize_naive(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=CHICAGO_TZ)
        return v

    @model_validator(mode="after")
    def _validate(self) -> WatchOverride:
        if self.status is ParkingStatus.UNKNOWN:
            raise ValueError("status must be LEGAL, NOT_LEGAL, or LEGAL_UNTIL")
        if self.status is ParkingStatus.LEGAL_UNTIL and self.move_by is None:
            raise ValueError("move_by is required when status is LEGAL_UNTIL")
        return self


def _new_id() -> str:
    return "wch_" + secrets.token_hex(6)


def _new_manage_token() -> str:
    """Opaque per-watch capability token. Grants management (unsubscribe / replace)
    of THIS watch only. Not PII; lives in watches.json in the private data repo and
    in the management links inside that watch's own emails."""
    return secrets.token_urlsafe(24)


class Watch(BaseModel):
    watch_id: str = Field(default_factory=_new_id)
    manage_token: str = Field(default_factory=_new_manage_token)
    location_id: str
    start_time: datetime
    end_time: datetime
    permit_zone: str | None = None

    status: WatchStatus = WatchStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=CHICAGO_TZ))

    last_decision: str | None = None          # last ParkingStatus seen
    last_checked_at: datetime | None = None
    notified: list[str] = Field(
        default_factory=list,
        description="Keys of messages already sent, e.g. 'morning:2026-09-08', 'urgent:ab12cd34'.",
    )
    override: WatchOverride | None = None

    @field_validator("start_time", "end_time", "created_at", "last_checked_at")
    @classmethod
    def _localize_naive(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=CHICAGO_TZ)
        return v

    def is_active(self, now: datetime) -> bool:
        return self.status == WatchStatus.ACTIVE and now < self.end_time
