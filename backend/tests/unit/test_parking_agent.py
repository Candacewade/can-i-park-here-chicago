"""run_parking_agent degrades to a deterministic-only result when the Claude
runtime is absent -- the live checker never goes down with the AI layer."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.agent import parking_agent as pa
from app.config import CHICAGO_TZ
from app.models.requests import ParkingRequest

_CORE = {
    "run_id": "r",
    "decision": {
        "status": "NOT_LEGAL",
        "move_by": None,
        "move_by_display": None,
        "start_time_display": "Monday, May 4, 2026 at 7:00 PM",
        "end_time_display": "Tuesday, May 5, 2026 at 9:00 AM",
        "urgent_alert": True,
        "urgent_reason": "A verified restriction prevents parking here.",
        "reasons": [
            {"category": "residential", "verdict": "blocks", "detail": "Zone 143 required."},
            {"category": "street_cleaning", "verdict": "allows", "detail": "None scheduled."},
        ],
        "unknown_reasons": [],
    },
    "completeness": {"complete": True, "missing": []},
}


@pytest.fixture
def _req():
    now = datetime.now(tz=CHICAGO_TZ)
    return ParkingRequest(location_id="x", start_time=now, end_time=now + timedelta(hours=12))


@pytest.fixture(autouse=True)
def _canned_core(monkeypatch):
    monkeypatch.setattr(pa, "_core_decision", lambda request, run_id: _CORE)


async def test_deterministic_fallback_when_no_cli(monkeypatch, _req):
    monkeypatch.setattr(pa, "resolve_claude_cli", lambda: None)

    result = await pa.run_parking_agent(_req)

    assert result.agent_available is False
    assert result.model == "deterministic"
    assert result.tool_calls == []
    assert result.decision_status == "NOT_LEGAL"
    # the explanation is a real, grounded template
    assert "cannot legally park" in result.final_text.lower()
    assert "Zone 143 required." in result.final_text
    assert "deterministic rule engine" in result.final_text
    assert "unavailable" in result.final_text.lower()


async def test_require_agent_raises_when_no_cli(monkeypatch, _req):
    monkeypatch.setattr(pa, "resolve_claude_cli", lambda: None)
    with pytest.raises(pa.AgentAuthError):
        await pa.run_parking_agent(_req, require_agent=True)


def test_deterministic_explanation_handles_each_status():
    for status in ("LEGAL", "LEGAL_UNTIL", "NOT_LEGAL", "UNKNOWN"):
        payload = {"decision": {**_CORE["decision"], "status": status}}
        text = pa._deterministic_explanation(payload)
        assert text and "rule engine" in text
