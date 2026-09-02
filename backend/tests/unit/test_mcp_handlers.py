"""The MCP handler layer after the 2026-09-01 inversion.

- evaluate_parking_request always runs the deterministic core itself
- skipping the (optional) investigation tools is fine -- the core still decides
- a core data-source failure -> UNKNOWN
- agent-added weather evidence can change the snow_route verdict, never the rest
"""

from __future__ import annotations

import pytest

from app import evidence_store
from app.mcp import handlers
from app.models.evidence import (
    EvidenceStatus,
    ResidentialZoneEvidence,
    SnowRouteEvidence,
    StreetCleaningEvidence,
    TemporaryClosureEvidence,
    WeatherOutlookEvidence,
)
from app.rules import gather as gather_mod

LOC = "wrightwood-3300w-north"
# A winter interval so snow_route is part of the required core.
START = "2026-01-20T19:00:00-06:00"
END = "2026-01-21T09:00:00-06:00"


def _res(zone=None, status=EvidenceStatus.VERIFIED):
    return ResidentialZoneEvidence(status=status, zone_required=zone)


@pytest.fixture(autouse=True)
def _stub_core(monkeypatch):
    """Deterministic core clients return canned, all-clear evidence."""
    evidence_store.reset()
    monkeypatch.setattr(gather_mod, "get_residential_zone_evidence", lambda loc: _res())
    monkeypatch.setattr(
        gather_mod, "get_street_cleaning_evidence",
        lambda loc, s, e: StreetCleaningEvidence(status=EvidenceStatus.VERIFIED, windows=[]),
    )
    monkeypatch.setattr(
        gather_mod, "get_street_closure_evidence",
        lambda loc, s, e: TemporaryClosureEvidence(status=EvidenceStatus.VERIFIED, closures=[]),
    )
    monkeypatch.setattr(
        gather_mod, "get_snow_route_evidence",
        lambda loc, s, e: SnowRouteEvidence(
            status=EvidenceStatus.VERIFIED, is_two_inch_route=False
        ),
    )
    yield
    evidence_store.reset()


def _evaluate(run="r1", permit=None):
    return handlers.evaluate_parking_request(run, LOC, START, END, permit)


def test_core_alone_produces_a_decision_no_investigation_needed():
    out = _evaluate()
    assert out["decision"]["status"] == "LEGAL"
    assert out["completeness"]["complete"] is True


def test_core_service_failure_yields_unknown(monkeypatch):
    monkeypatch.setattr(
        gather_mod, "get_street_cleaning_evidence",
        lambda loc, s, e: StreetCleaningEvidence(
            status=EvidenceStatus.UNAVAILABLE, notes=["portal 503"]
        ),
    )
    out = _evaluate()
    assert out["decision"]["status"] == "UNKNOWN"
    assert any("street_cleaning" in m for m in out["completeness"]["missing"])


def test_residential_blocker_is_not_legal(monkeypatch):
    monkeypatch.setattr(gather_mod, "get_residential_zone_evidence", lambda loc: _res(zone="1439"))
    out = _evaluate(permit=None)
    assert out["decision"]["status"] == "NOT_LEGAL"
    assert out["decision"]["urgent_alert"] is True


def test_agent_weather_evidence_flips_snow_route(monkeypatch):
    monkeypatch.setattr(
        gather_mod, "get_snow_route_evidence",
        lambda loc, s, e: SnowRouteEvidence(
            status=EvidenceStatus.VERIFIED, is_two_inch_route=True, on_street="W WRIGHTWOOD AVE"
        ),
    )
    run = "r-snow"
    # before weather: advisory only -> still LEGAL
    assert _evaluate(run)["decision"]["status"] == "LEGAL"

    # agent stores a verified >=2in forecast for this run + block + interval
    from app.mcp.handlers import _parse_dt
    evidence_store.record(
        run, evidence_store.WEATHER, location_id=LOC,
        evidence=WeatherOutlookEvidence(status=EvidenceStatus.VERIFIED, expected_snow_inches=3.4),
        start=_parse_dt(START), end=_parse_dt(END),
    )
    after = _evaluate(run)
    assert after["decision"]["status"] == "NOT_LEGAL"
    assert any(r["category"] == "snow_route" and r["verdict"] == "blocks"
               for r in after["decision"]["reasons"])


def test_permit_none_string_is_no_permit():
    out = handlers.evaluate_parking_request("r2", LOC, START, END, "none")
    assert "error" not in out
    assert out["decision"]["status"] == "LEGAL"


def test_find_legal_parking_nearby_returns_options(monkeypatch):
    # all blocks evaluate LEGAL under the stubbed core
    out = handlers.find_legal_parking_nearby_tool("r3", LOC, START, END, None)
    assert isinstance(out["options"], list)
    assert all("location_id" in o and "walk_minutes" in o for o in out["options"])
