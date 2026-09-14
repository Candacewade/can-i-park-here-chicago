"""End-to-end monitor pass with the agent disabled and data stubbed."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.config import CHICAGO_TZ
from app.models.decision import ParkingDecision, ParkingStatus
from app.models.evidence import (
    EvidenceStatus,
    ParkingEvidence,
    ResidentialZoneEvidence,
    StreetCleaningEvidence,
    TemporaryClosureEvidence,
)
from app.monitor import run as run_mod
from app.monitor.models import Watch, WatchOverride, WatchStatus
from app.monitor.run import run_monitor

NOW = datetime(2026, 9, 8, 8, 0, tzinfo=CHICAGO_TZ)


class MemStore:
    def __init__(self, watches):
        self._w = {w.watch_id: w for w in watches}
        self.saved = 0

    def load(self):
        return self._w

    def save(self, watches):
        self._w = watches
        self.saved += 1


@pytest.fixture
def sent(monkeypatch):
    box: list[tuple[str, str, str, str | None]] = []

    def _send(to, subj, body, html=None):
        box.append((to, subj, body, html))
        return "sent"

    monkeypatch.setattr(run_mod, "send_email", _send)
    monkeypatch.setattr(run_mod.notify, "get_email", lambda wid: "driver@example.com")
    # keep compose_email's alternatives lookup off the live City API
    from app.monitor import compose as compose_mod
    monkeypatch.setattr(compose_mod, "find_legal_parking_nearby", lambda *a, **k: [])
    return box


def _stub_decision(
    monkeypatch, status=ParkingStatus.LEGAL, move_by=None, urgent=False, reason=None
):
    monkeypatch.setattr(
        run_mod, "gather_evidence",
        lambda req: ParkingEvidence(
            residential=ResidentialZoneEvidence(status=EvidenceStatus.VERIFIED),
            street_cleaning=StreetCleaningEvidence(status=EvidenceStatus.VERIFIED),
            temporary_closure=TemporaryClosureEvidence(status=EvidenceStatus.VERIFIED),
        ),
    )
    monkeypatch.setattr(
        run_mod, "evaluate_parking",
        lambda req, ev: ParkingDecision(
            status=status, move_by=move_by, urgent_alert=urgent, urgent_reason=reason,
            start_time_display="A", end_time_display="B",
            move_by_display="MOVE BY X" if move_by else None,
        ),
    )


def _watch(**kw):
    base = dict(
        watch_id="wch_test01",
        location_id="wrightwood-3300w-north",
        start_time=NOW - timedelta(hours=2),
        end_time=NOW + timedelta(days=10),
    )
    base.update(kw)
    return Watch(**base)


async def test_morning_email_sent_and_recorded(monkeypatch, sent):
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    store = MemStore([_watch()])
    report = await run_monitor(now=NOW, store=store, use_agent=False)

    assert report.checked == 1
    assert report.emails_sent == 1
    assert sent[0][0] == "driver@example.com"
    w = store.load()["wch_test01"]
    assert w.last_decision == "LEGAL"
    assert any(k.startswith("morning:") for k in w.notified)


async def test_no_duplicate_morning_same_day(monkeypatch, sent):
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    w = _watch(notified=["morning:2026-09-08"])
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False)
    assert report.emails_sent == 0


async def test_urgent_alert_email(monkeypatch, sent):
    _stub_decision(
        monkeypatch, ParkingStatus.NOT_LEGAL, urgent=True, reason="zone 143 permit required"
    )
    report = await run_monitor(now=NOW, store=MemStore([_watch()]), use_agent=False)
    assert report.emails_sent == 1
    assert "Urgent parking alert" in sent[0][1]
    # HTML + plain-text parts both present, real HTML hierarchy (not Markdown)
    _, _, body_text, body_html = sent[0]
    assert body_html and "<h1" in body_html and "<hr" in body_html
    assert "##" not in body_html and "**" not in body_html
    assert "<" not in body_text


async def test_no_destination_still_updates_state_but_sends_nothing(monkeypatch):
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    monkeypatch.setattr(run_mod.notify, "get_email", lambda wid: None)
    monkeypatch.setattr(run_mod, "send_email", lambda *a: pytest.fail("should not send"))
    store = MemStore([_watch()])
    report = await run_monitor(now=NOW, store=store, use_agent=False)
    assert report.emails_sent == 0
    assert store.load()["wch_test01"].last_decision == "LEGAL"
    assert report.outcomes[0].note


async def test_expired_watch_is_marked(monkeypatch, sent):
    """Expiry is calendar-day based: a watch only expires the day AFTER its
    end_time's date, not the instant end_time passes (see test below)."""
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    w = _watch(end_time=NOW - timedelta(days=1))
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False)
    assert report.checked == 0
    assert w.status is WatchStatus.EXPIRED


async def test_watch_still_checked_on_its_final_calendar_day(monkeypatch, sent):
    """end_time already passed earlier TODAY -- still the watch's last day, so
    it's still checked (and sent the FINAL_DAY email, not silently dropped)."""
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    w = _watch(end_time=NOW - timedelta(hours=1))
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False)
    assert report.checked == 1
    assert w.status is WatchStatus.ACTIVE
    assert report.emails_sent == 1
    assert "last day" in sent[0][1].lower()


async def test_no_more_emails_the_day_after_final_day(monkeypatch, sent):
    """The morning after the final-day email: the watch expires and sends
    nothing further -- no more emails until the user sets up a new watch."""
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    w = _watch(end_time=NOW - timedelta(hours=1), notified=[f"final_day:{NOW.date().isoformat()}"])
    next_morning = NOW + timedelta(days=1)
    report = await run_monitor(now=next_morning, store=MemStore([w]), use_agent=False)
    assert report.checked == 0
    assert report.emails_sent == 0
    assert w.status is WatchStatus.EXPIRED


# --- urgent-only (hourly poll) mode --------------------------------

async def test_urgent_only_quiet_poll_touches_nothing(monkeypatch, sent):
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    w = _watch()
    store = MemStore([w])
    report = await run_monitor(now=NOW, store=store, use_agent=False, urgent_only=True)

    assert report.mode == "urgent_only"
    assert report.emails_sent == 0
    assert w.last_checked_at is None        # state untouched on a quiet poll
    assert w.last_decision is None
    assert report.outcomes[0].status == "LEGAL"


async def test_urgent_only_sends_on_new_urgent_condition(monkeypatch, sent):
    _stub_decision(
        monkeypatch, ParkingStatus.NOT_LEGAL, urgent=True, reason="new closure permit"
    )
    w = _watch()
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False, urgent_only=True)

    assert report.emails_sent == 1
    assert "Urgent parking alert" in sent[0][1]
    assert any(k.startswith("urgent:") for k in w.notified)


async def test_urgent_only_does_not_resend_same_cause(monkeypatch, sent):
    _stub_decision(
        monkeypatch, ParkingStatus.NOT_LEGAL, urgent=True, reason="new closure permit"
    )
    from app.monitor.schedule import urgent_cause_key

    cause = urgent_cause_key(
        ParkingDecision(status=ParkingStatus.NOT_LEGAL, urgent_alert=True,
                        urgent_reason="new closure permit")
    )
    w = _watch(notified=[cause])
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False, urgent_only=True)
    assert report.emails_sent == 0


async def test_urgent_only_ignores_morning_and_reminders(monkeypatch, sent):
    _stub_decision(monkeypatch, ParkingStatus.LEGAL_UNTIL, move_by=NOW + timedelta(days=3))
    report = await run_monitor(
        now=NOW, store=MemStore([_watch()]), use_agent=False, urgent_only=True
    )
    assert report.emails_sent == 0   # morning + reminder-3d would fire in full mode


async def test_use_agent_true_but_no_cli_falls_back(monkeypatch, sent):
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    monkeypatch.setattr(run_mod, "resolve_claude_cli", lambda: None)
    report = await run_monitor(now=NOW, store=MemStore([_watch()]), use_agent=True)
    assert report.agent_used is False
    assert report.emails_sent == 1   # deterministic template still sends


# --- self-reported override: full override, either direction --------

async def test_active_override_replaces_the_city_data_decision(monkeypatch, sent):
    """City data says LEGAL; the user reported NOT_LEGAL (e.g. a sign they saw).
    The override wins outright -- this is the feature working as designed."""
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    w = _watch(override=WatchOverride(
        status=ParkingStatus.NOT_LEGAL,
        note="Orange street cleaning sign posted, not in the app's data",
        expires_at=NOW + timedelta(days=1),
    ))
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False)

    assert report.outcomes[0].status == "NOT_LEGAL"
    assert report.emails_sent == 1
    assert "Urgent" in sent[0][1]  # NOT_LEGAL is always urgent, override or not
    assert "you reported" in sent[0][2].lower()
    assert w.last_decision == "NOT_LEGAL"


async def test_override_can_also_relax_a_real_restriction(monkeypatch, sent):
    """City data says NOT_LEGAL; the user reported LEGAL. By explicit design
    choice this is a full, bidirectional override -- see docs/monitoring.md."""
    _stub_decision(monkeypatch, ParkingStatus.NOT_LEGAL, urgent=True, reason="permit required")
    w = _watch(override=WatchOverride(
        status=ParkingStatus.LEGAL,
        note="Sign says this restriction ended last month",
        expires_at=NOW + timedelta(days=1),
    ))
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False)
    assert report.outcomes[0].status == "LEGAL"


async def test_expired_override_no_longer_applies(monkeypatch, sent):
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    w = _watch(override=WatchOverride(
        status=ParkingStatus.NOT_LEGAL,
        note="stale report",
        expires_at=NOW - timedelta(hours=1),  # already expired
    ))
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False)
    assert report.outcomes[0].status == "LEGAL"  # back to city data


async def test_override_skips_agent_investigation(monkeypatch, sent):
    """The agent must not run while an override is active -- it would re-derive
    (and could silently reinstate) the real city-data verdict."""
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    called = False

    async def _fake_investigate(request, decision):
        nonlocal called
        called = True
        return decision, "agent prose"

    monkeypatch.setattr(run_mod, "_investigate", _fake_investigate)
    w = _watch(override=WatchOverride(
        status=ParkingStatus.NOT_LEGAL, note="sign", expires_at=NOW + timedelta(days=1),
    ))
    await run_monitor(now=NOW, store=MemStore([w]), use_agent=True)
    assert called is False


async def test_override_email_includes_source_notice(monkeypatch, sent):
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    w = _watch(override=WatchOverride(
        status=ParkingStatus.NOT_LEGAL,
        note="Orange sign, Thu 9am-2pm",
        expires_at=NOW + timedelta(days=1),
    ))
    await run_monitor(now=NOW, store=MemStore([w]), use_agent=False)
    assert "not verified city data" in sent[0][2].lower()
    assert "Orange sign, Thu 9am-2pm" in sent[0][2]


async def test_no_override_behaves_exactly_as_before(monkeypatch, sent):
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    report = await run_monitor(now=NOW, store=MemStore([_watch()]), use_agent=False)
    assert report.outcomes[0].status == "LEGAL"
    assert "you reported" not in sent[0][2].lower()


# --- resolved / unsubscribed watches never notify -------------------

async def test_resolved_watch_produces_no_daily_email(monkeypatch, sent):
    _stub_decision(monkeypatch, ParkingStatus.NOT_LEGAL, urgent=True, reason="permit")
    w = _watch(status=WatchStatus.RESOLVED)
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False)
    assert report.checked == 0
    assert report.emails_sent == 0


async def test_resolved_watch_produces_no_urgent_email(monkeypatch, sent):
    _stub_decision(monkeypatch, ParkingStatus.NOT_LEGAL, urgent=True, reason="permit")
    w = _watch(status=WatchStatus.RESOLVED)
    report = await run_monitor(
        now=NOW, store=MemStore([w]), use_agent=False, urgent_only=True
    )
    assert report.checked == 0
    assert report.emails_sent == 0


# --- after an extend: the endpoint dropped reminder keys, kept morning/urgent --

async def test_after_extend_new_restriction_reminder_fires(monkeypatch, sent):
    """The extend endpoint drops reminder:* keys. A newly-relevant move-by three
    days out then still produces the T-3d reminder that the old (already-sent)
    key would have suppressed."""
    move_by = NOW + timedelta(days=3)  # exactly REMINDER_DAYS_AHEAD
    _stub_decision(monkeypatch, ParkingStatus.LEGAL_UNTIL, move_by=move_by)
    w = _watch(
        end_time=NOW + timedelta(days=20),
        notified=["morning:2026-09-08", "urgent:oldcause"],  # reminder:* already dropped
    )
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False)
    assert report.emails_sent == 1
    assert "REMINDER_3D" in report.outcomes[0].messages


async def test_after_extend_unchanged_urgent_cause_not_resent(monkeypatch, sent):
    _stub_decision(
        monkeypatch, ParkingStatus.NOT_LEGAL, urgent=True, reason="zone 100 permit required"
    )
    from app.monitor.schedule import urgent_cause_key

    cause = urgent_cause_key(
        ParkingDecision(status=ParkingStatus.NOT_LEGAL, urgent_alert=True,
                        urgent_reason="zone 100 permit required")
    )
    w = _watch(notified=["morning:2026-09-08", cause])
    report = await run_monitor(
        now=NOW, store=MemStore([w]), use_agent=False, urgent_only=True
    )
    assert report.emails_sent == 0   # same cause hash -> no duplicate alert
