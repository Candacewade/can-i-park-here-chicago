from datetime import datetime, timedelta

from app.config import CHICAGO_TZ
from app.models.decision import ParkingDecision, ParkingStatus
from app.monitor.models import Watch
from app.monitor.schedule import MessageType, due_messages, notified_key, primary

NOW = datetime(2026, 9, 8, 8, 0, tzinfo=CHICAGO_TZ)


def _watch(notified=None):
    return Watch(
        location_id="x",
        start_time=NOW - timedelta(days=1),
        end_time=NOW + timedelta(days=10),
        notified=notified or [],
    )


def _decision(status=ParkingStatus.LEGAL, move_by=None, urgent=False, reason=None):
    return ParkingDecision(
        status=status, move_by=move_by, urgent_alert=urgent, urgent_reason=reason
    )


def test_morning_due_once_per_day():
    d = _decision()
    assert MessageType.MORNING in due_messages(_watch(), d, NOW)
    key = notified_key(MessageType.MORNING, d, NOW)
    assert MessageType.MORNING not in due_messages(_watch([key]), d, NOW)


def test_urgent_due_when_flagged_and_not_yet_sent():
    d = _decision(status=ParkingStatus.NOT_LEGAL, urgent=True, reason="zone 143 required")
    due = due_messages(_watch(), d, NOW)
    assert MessageType.URGENT in due
    key = notified_key(MessageType.URGENT, d, NOW)
    assert MessageType.URGENT not in due_messages(_watch([key]), d, NOW)


def test_reminder_3d_fires_exactly_three_days_before():
    move_by = datetime(2026, 9, 11, 9, tzinfo=CHICAGO_TZ)  # NOW is Sep 8
    d = _decision(status=ParkingStatus.LEGAL_UNTIL, move_by=move_by)
    assert MessageType.REMINDER_3D in due_messages(_watch(), d, NOW)
    # not two days before
    two_before = datetime(2026, 9, 9, 8, tzinfo=CHICAGO_TZ)
    assert MessageType.REMINDER_3D not in due_messages(_watch(), d, two_before)


def test_night_before_needs_evening_hour():
    move_by = datetime(2026, 9, 9, 9, tzinfo=CHICAGO_TZ)
    d = _decision(status=ParkingStatus.LEGAL_UNTIL, move_by=move_by)
    morning_before = datetime(2026, 9, 8, 8, tzinfo=CHICAGO_TZ)
    evening_before = datetime(2026, 9, 8, 19, tzinfo=CHICAGO_TZ)
    assert MessageType.REMINDER_NIGHT_BEFORE not in due_messages(_watch(), d, morning_before)
    assert MessageType.REMINDER_NIGHT_BEFORE in due_messages(_watch(), d, evening_before)


def test_priority_urgent_beats_morning():
    assert primary([MessageType.MORNING, MessageType.URGENT]) is MessageType.URGENT
    assert primary([]) is None
