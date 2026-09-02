"""Watch model. Deliberately carries NO personally identifying information --
this object is serialized into a repo-committed watches.json."""

from __future__ import annotations

import secrets
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.config import CHICAGO_TZ


class WatchStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"   # the car was moved / the user cancelled
    EXPIRED = "expired"     # the planned end_time passed


def _new_id() -> str:
    return "wch_" + secrets.token_hex(6)


class Watch(BaseModel):
    watch_id: str = Field(default_factory=_new_id)
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

    def is_active(self, now: datetime) -> bool:
        return self.status == WatchStatus.ACTIVE and now < self.end_time
