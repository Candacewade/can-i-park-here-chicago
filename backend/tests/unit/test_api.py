
import pytest
from fastapi.testclient import TestClient

from app.agent.parking_agent import AgentRunResult, ToolCallTrace
from app.api import main as api_main
from app.models.requests import ParkingRequest

client = TestClient(api_main.app)


def test_health():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "agent_runtime" in body


def test_locations_tree_shape():
    body = client.get("/api/locations").json()
    assert body["neighborhoods"]
    nb = body["neighborhoods"][0]
    assert nb["name"] == "Logan Square"
    street = nb["streets"][0]
    assert street["blocks"][0]["sides"][0]["location_id"]


_DECISION = {
    "decision": {
        "status": "LEGAL_UNTIL",
        "move_by": "2026-09-09T09:00:00-05:00",
        "move_by_display": "Wednesday, September 9, 2026 at 9:00 AM",
        "start_time_display": "Tuesday, September 8, 2026 at 7:00 PM",
        "end_time_display": "Wednesday, September 9, 2026 at 11:00 AM",
        "urgent_alert": False,
        "urgent_reason": None,
        "reasons": [{"category": "street_cleaning", "verdict": "limits", "detail": "x"}],
        "unknown_reasons": [],
    },
    "completeness": {"complete": True, "missing": []},
}


@pytest.fixture
def _fake_agent(monkeypatch):
    async def fake_run(request: ParkingRequest) -> AgentRunResult:
        return AgentRunResult(
            request=request,
            final_text="You must move by 9 AM.",
            run_id="run-xyz",
            tool_calls=[
                ToolCallTrace(
                    order=1, name="mcp__chicago-parking__get_weather_outlook",
                    arguments={"run_id": "run-xyz"}, result={"status": "VERIFIED"},
                    latency_ms=12.0,
                )
            ],
            core_decision=_DECISION,
            decision=_DECISION,
        )

    monkeypatch.setattr(api_main, "run_parking_agent", fake_run)
    monkeypatch.setattr(api_main, "resolve_claude_cli", lambda: "/fake/claude")


def test_analyze_happy_path(_fake_agent):
    resp = client.post(
        "/api/parking/analyze",
        json={
            "location_id": "wrightwood-3300w-north",
            "start_time": "2026-09-08T19:00:00",
            "end_time": "2026-09-09T11:00:00",
            "permit_zone": "100",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "LEGAL_UNTIL"
    assert body["move_by_display"] == "Wednesday, September 9, 2026 at 9:00 AM"
    assert body["trace"][0]["name"] == "get_weather_outlook"
    assert body["run_id"] == "run-xyz"


def test_analyze_rejects_end_before_start(_fake_agent):
    resp = client.post(
        "/api/parking/analyze",
        json={
            "location_id": "x",
            "start_time": "2026-09-09T11:00:00",
            "end_time": "2026-09-08T19:00:00",
        },
    )
    assert resp.status_code == 422


def test_analyze_503_when_no_agent_runtime(monkeypatch):
    monkeypatch.setattr(api_main, "resolve_claude_cli", lambda: None)
    resp = client.post(
        "/api/parking/analyze",
        json={
            "location_id": "wrightwood-3300w-north",
            "start_time": "2026-09-08T19:00:00",
            "end_time": "2026-09-09T11:00:00",
        },
    )
    assert resp.status_code == 503
