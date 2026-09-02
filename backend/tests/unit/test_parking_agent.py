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


def test_replay_agent_evidence_reinjects_into_parent_store():
    """The agent gathers optional evidence in the MCP subprocess; the parent's
    post-agent re-eval must see it via _replay_agent_evidence."""
    from app import evidence_store
    from app.agent.parking_agent import AgentRunResult, ToolCallTrace, _replay_agent_evidence
    from app.models.requests import ParkingRequest

    evidence_store.reset()
    now = datetime.now(tz=CHICAGO_TZ)
    req = ParkingRequest(location_id="x", start_time=now, end_time=now + timedelta(hours=12))
    result = AgentRunResult(request=req, final_text="", run_id="r-replay")
    result.tool_calls = [
        ToolCallTrace(
            order=1, name="mcp__chicago-parking__get_weather_outlook",
            arguments={
                "run_id": "r-replay", "location_id": "x",
                "start_time": req.start_time.isoformat(), "end_time": req.end_time.isoformat(),
            },
            result={"status": "VERIFIED", "expected_snow_inches": 3.4},
        )
    ]

    _replay_agent_evidence(result)

    got = evidence_store.verdict_relevant_evidence(
        "r-replay", location_id="x", start=req.start_time, end=req.end_time
    )
    assert evidence_store.WEATHER in got
    assert got[evidence_store.WEATHER].expected_snow_inches == 3.4
    evidence_store.reset()
