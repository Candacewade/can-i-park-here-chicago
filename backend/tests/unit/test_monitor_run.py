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
from app.monitor.models import Watch, WatchStatus
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
    box: list[tuple[str, str]] = []
    monkeypatch.setattr(
        run_mod, "send_email", lambda to, subj, body: (box.append((to, subj)), "sent")[1]
    )
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
    assert sent[0][1].startswith("URGENT")


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
    _stub_decision(monkeypatch, ParkingStatus.LEGAL)
    w = _watch(end_time=NOW - timedelta(hours=1))
    report = await run_monitor(now=NOW, store=MemStore([w]), use_agent=False)
    assert report.checked == 0
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
    assert sent[0][1].startswith("URGENT")
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
