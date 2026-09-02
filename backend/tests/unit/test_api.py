
import pytest
from fastapi.testclient import TestClient

from app.agent.parking_agent import AgentRunResult, ToolCallTrace
from app.api import main as api_main
from app.models.requests import ParkingRequest

client = TestClient(api_main.app)


def test_health():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "agent_available" in body


def test_examples_endpoint():
    body = client.get("/api/locations/examples").json()
    assert isinstance(body, list) and body
    assert {"label", "number", "street", "zip_code"} <= body[0].keys()


def test_resolve_endpoint(monkeypatch):
    from app.locations.registry import ChicagoParkingLocation
    from app.locations.resolve import ResolvedLocation

    def mk(s):
        return ChicagoParkingLocation(
            location_id=f"n-clark-st-2400-{s}", neighborhood="Lincoln Park",
            street_name="N Clark St", from_cross_street="W Fullerton Pkwy",
            to_cross_street="W Arlington Pl", side=s, address_parity="even",
            address_number=2400, address_range_low=2400, address_range_high=2444,
            street_sweeping_ward="43", street_sweeping_section="03",
            latitude=41.9256, longitude=-87.6406,
        )

    def fake_resolve(number, street, zip_code, side=None):
        return ResolvedLocation(
            query="2400 N Clark St", in_chicago=True,
            matched_address="2400 N CLARK ST, CHICAGO, IL, 60614",
            neighborhood="Lincoln Park", suggested_side="west", side_confidence="high",
            side_options=["east", "west"],
            locations={"east": mk("east"), "west": mk("west")},
        )

    monkeypatch.setattr(api_main, "resolve_address", fake_resolve)
    monkeypatch.setattr(api_main, "remember_location", lambda loc: None)

    r = client.post(
        "/api/locations/resolve",
        json={"number": 2400, "street": "N Clark St", "zip_code": "60614"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["in_chicago"] is True
    assert body["neighborhood"] == "Lincoln Park"
    assert body["suggested_side"] == "west"
    assert {c["side"] for c in body["side_options"]} == {"east", "west"}
    assert body["street_sweeping_ward"] == "43"


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


def _fake_result(request, *, agent_available=True):
    return AgentRunResult(
        request=request,
        final_text="You must move by 9 AM." if agent_available else "(deterministic template)",
        run_id="run-xyz",
        agent_available=agent_available,
        model="claude-sonnet-4-5" if agent_available else "deterministic",
        tool_calls=(
            [ToolCallTrace(
                order=1, name="mcp__chicago-parking__get_weather_outlook",
                arguments={"run_id": "run-xyz"}, result={"status": "VERIFIED"}, latency_ms=12.0,
            )] if agent_available else []
        ),
        core_decision=_DECISION,
        decision=_DECISION,
    )


@pytest.fixture
def _fake_agent(monkeypatch):
    async def fake_run(request: ParkingRequest, *, require_agent=False) -> AgentRunResult:
        return _fake_result(request)

    monkeypatch.setattr(api_main, "run_parking_agent", fake_run)


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
    assert body["agent_available"] is True


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


def test_analyze_degrades_without_agent(monkeypatch):
    async def fake_run(request: ParkingRequest, *, require_agent=False):
        return _fake_result(request, agent_available=False)

    monkeypatch.setattr(api_main, "run_parking_agent", fake_run)
    resp = client.post(
        "/api/parking/analyze",
        json={
            "location_id": "wrightwood-3300w-north",
            "start_time": "2026-09-08T19:00:00",
            "end_time": "2026-09-09T11:00:00",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "LEGAL_UNTIL"       # the verdict still comes through
    assert body["agent_available"] is False
    assert body["trace"] == []
    assert body["summary"]
