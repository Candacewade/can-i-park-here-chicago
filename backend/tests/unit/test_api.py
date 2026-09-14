
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


def _mk_location(s):
    from app.locations.registry import ChicagoParkingLocation

    return ChicagoParkingLocation(
        location_id=f"n-clark-st-2400-{s}", neighborhood="Lincoln Park",
        street_name="N Clark St", from_cross_street="W Fullerton Pkwy",
        to_cross_street="W Arlington Pl", side=s, address_parity="even",
        address_number=2400, address_range_low=2400, address_range_high=2444,
        street_sweeping_ward="43", street_sweeping_section="03",
        latitude=41.9256, longitude=-87.6406,
    )


def _fake_resolve_two_sides(number, street, zip_code, side=None):
    from app.locations.resolve import ResolvedLocation

    return ResolvedLocation(
        query="2400 N Clark St", in_chicago=True,
        matched_address="2400 N CLARK ST, CHICAGO, IL, 60614",
        neighborhood="Lincoln Park", suggested_side="west", side_confidence="high",
        side_options=["east", "west"],
        locations={"east": _mk_location("east"), "west": _mk_location("west")},
    )


def test_resolve_endpoint(monkeypatch):
    from app.models.evidence import EvidenceStatus, ResidentialZoneEvidence

    monkeypatch.setattr(api_main, "resolve_address", _fake_resolve_two_sides)
    monkeypatch.setattr(api_main, "remember_location", lambda loc: None)
    monkeypatch.setattr(
        api_main, "get_residential_zone_evidence",
        lambda loc: ResidentialZoneEvidence(status=EvidenceStatus.UNAVAILABLE),
    )

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


# --- resolve: required_permit_zone, straight from City data, not a guess ---

def _zone_evidence(status, zone_required=None, is_buffer=False):
    from app.models.evidence import EvidenceStatus, ResidentialZoneEvidence

    return ResidentialZoneEvidence(
        status=EvidenceStatus[status], zone_required=zone_required, is_buffer=is_buffer,
    )


def test_resolve_surfaces_the_verified_required_zone(monkeypatch):
    monkeypatch.setattr(api_main, "resolve_address", _fake_resolve_two_sides)
    monkeypatch.setattr(api_main, "remember_location", lambda loc: None)
    monkeypatch.setattr(
        api_main, "get_residential_zone_evidence",
        lambda loc: _zone_evidence("VERIFIED", zone_required="143"),
    )

    r = client.post(
        "/api/locations/resolve",
        json={"number": 2400, "street": "N Clark St", "zip_code": "60614"},
    )
    for c in r.json()["side_options"]:
        assert c["required_permit_zone"] == "143"
        assert c["permit_zone_is_buffer"] is False


def test_resolve_surfaces_buffer_zone(monkeypatch):
    monkeypatch.setattr(api_main, "resolve_address", _fake_resolve_two_sides)
    monkeypatch.setattr(api_main, "remember_location", lambda loc: None)
    monkeypatch.setattr(
        api_main, "get_residential_zone_evidence",
        lambda loc: _zone_evidence("VERIFIED", zone_required="100", is_buffer=True),
    )

    r = client.post(
        "/api/locations/resolve",
        json={"number": 2400, "street": "N Clark St", "zip_code": "60614"},
    )
    assert r.json()["side_options"][0]["permit_zone_is_buffer"] is True


def test_resolve_omits_zone_when_lookup_unavailable(monkeypatch):
    """A failed/unavailable zone lookup must never surface a fabricated zone --
    it's just silently omitted, same as any other best-effort enrichment."""
    monkeypatch.setattr(api_main, "resolve_address", _fake_resolve_two_sides)
    monkeypatch.setattr(api_main, "remember_location", lambda loc: None)
    monkeypatch.setattr(
        api_main, "get_residential_zone_evidence",
        lambda loc: _zone_evidence("UNAVAILABLE"),
    )

    r = client.post(
        "/api/locations/resolve",
        json={"number": 2400, "street": "N Clark St", "zip_code": "60614"},
    )
    assert r.status_code == 200
    for c in r.json()["side_options"]:
        assert c["required_permit_zone"] is None


def test_resolve_survives_zone_lookup_raising(monkeypatch):
    def boom(loc):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(api_main, "resolve_address", _fake_resolve_two_sides)
    monkeypatch.setattr(api_main, "remember_location", lambda loc: None)
    monkeypatch.setattr(api_main, "get_residential_zone_evidence", boom)

    r = client.post(
        "/api/locations/resolve",
        json={"number": 2400, "street": "N Clark St", "zip_code": "60614"},
    )
    assert r.status_code == 200
    assert r.json()["side_options"][0]["required_permit_zone"] is None


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
