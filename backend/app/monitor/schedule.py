"""Deterministic: given a watch, its fresh decision, and 'now', which
notification messages are due? No LLM anywhere in here."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from enum import IntEnum

from app.config import CHICAGO_TZ, REMINDER_DAYS_AHEAD, REMINDER_NIGHT_BEFORE_HOUR
from app.models.decision import ParkingDecision
from app.monitor.models import Watch


class MessageType(IntEnum):
    """Value = priority (higher wins when several are due in one run)."""

    MORNING = 1
    REMINDER_3D = 2
    REMINDER_NIGHT_BEFORE = 3
    URGENT = 4


def urgent_cause_key(decision: ParkingDecision) -> str:
    basis = decision.urgent_reason or decision.status.value
    return "urgent:" + hashlib.sha1(basis.encode()).hexdigest()[:8]


def notified_key(msg: MessageType, decision: ParkingDecision, now: datetime) -> str:
    today = now.astimezone(CHICAGO_TZ).date().isoformat()
    if msg is MessageType.MORNING:
        return f"morning:{today}"
    if msg is MessageType.URGENT:
        return urgent_cause_key(decision)
    if msg is MessageType.REMINDER_3D:
        return "reminder:3d"
    return "reminder:night"


def due_messages(watch: Watch, decision: ParkingDecision, now: datetime) -> list[MessageType]:
    now_local = now.astimezone(CHICAGO_TZ)
    today = now_local.date()
    due: list[MessageType] = []

    if f"morning:{today.isoformat()}" not in watch.notified:
        due.append(MessageType.MORNING)

    if decision.urgent_alert and urgent_cause_key(decision) not in watch.notified:
        due.append(MessageType.URGENT)

    if decision.move_by is not None:
        move_date = decision.move_by.astimezone(CHICAGO_TZ).date()
        if (
            today == move_date - timedelta(days=REMINDER_DAYS_AHEAD)
            and "reminder:3d" not in watch.notified
        ):
            due.append(MessageType.REMINDER_3D)
        if (
            today == move_date - timedelta(days=1)
            and now_local.hour >= REMINDER_NIGHT_BEFORE_HOUR
            and "reminder:night" not in watch.notified
        ):
            due.append(MessageType.REMINDER_NIGHT_BEFORE)

    return due


def primary(due: list[MessageType]) -> MessageType | None:
    return max(due) if due else None
