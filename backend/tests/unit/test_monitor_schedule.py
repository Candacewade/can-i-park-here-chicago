from datetime import datetime, timedelta

from app.config import CHICAGO_TZ
from app.models.decision import ParkingDecision, ParkingStatus
from app.monitor.models import Watch
from app.monitor.schedule import MessageType, due_messages, notified_key, primary

NOW = datetime(2026, 9, 8, 8, 0, tzinfo=CHICAGO_TZ)


def _watch(notified=None, end_time=None):
    return Watch(
        location_id="x",
        start_time=NOW - timedelta(days=1),
        end_time=end_time or NOW + timedelta(days=10),
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


# --- final day (last calendar day of the watch's requested window) --------

def test_final_day_replaces_morning_on_end_date():
    """end_time is later today -- this is the watch's last calendar day, so
    FINAL_DAY is due instead of MORNING."""
    w = _watch(end_time=NOW + timedelta(hours=3))
    due = due_messages(w, _decision(), NOW)
    assert MessageType.FINAL_DAY in due
    assert MessageType.MORNING not in due


def test_final_day_due_even_if_end_time_already_passed_today():
    """end_time was earlier today -- still today's calendar date, so the
    watch still gets its final-day email rather than going silent."""
    w = _watch(end_time=NOW - timedelta(hours=1))
    due = due_messages(w, _decision(), NOW)
    assert MessageType.FINAL_DAY in due


def test_final_day_sent_once():
    end_time = NOW + timedelta(hours=3)
    d = _decision()
    key = notified_key(MessageType.FINAL_DAY, d, NOW)
    w = _watch(notified=[key], end_time=end_time)
    assert MessageType.FINAL_DAY not in due_messages(w, d, NOW)


def test_morning_still_due_before_end_date():
    w = _watch(end_time=NOW + timedelta(days=2))
    due = due_messages(w, _decision(), NOW)
    assert MessageType.MORNING in due
    assert MessageType.FINAL_DAY not in due


def test_urgent_beats_final_day():
    assert primary([MessageType.FINAL_DAY, MessageType.URGENT]) is MessageType.URGENT


def test_no_morning_same_day_as_already_sent_final_day():
    """Extending on the final day (after that day's final_day email already
    went out) pushes end_date into the future -- must not also send a same-day
    morning email."""
    today_key = f"final_day:{NOW.date().isoformat()}"
    w = _watch(notified=[today_key], end_time=NOW + timedelta(days=5))  # extended
    due = due_messages(w, _decision(), NOW)
    assert MessageType.MORNING not in due
    assert MessageType.FINAL_DAY not in due


def test_final_day_beats_reminders():
    assert primary([MessageType.REMINDER_3D, MessageType.FINAL_DAY]) is MessageType.FINAL_DAY
    assert (
        primary([MessageType.REMINDER_NIGHT_BEFORE, MessageType.FINAL_DAY])
        is MessageType.FINAL_DAY
    )
