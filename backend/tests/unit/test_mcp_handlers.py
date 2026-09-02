"""The store-backed orchestration path: MCP evidence tools persist authoritative
output server-side, and evaluate_parking_request consumes only that.

Central guarantee under test: if the agent skips a required evidence tool, the
evidence is missing and the deterministic evaluator returns UNKNOWN.
"""

from __future__ import annotations

import pytest

from app import evidence_store
from app.mcp import handlers
from app.models.evidence import (
    EvidenceStatus,
    ResidentialZoneEvidence,
    StreetCleaningEvidence,
    TemporaryClosureEvidence,
)

LOC = "wrightwood-3300w-north"
START = "2026-09-20T19:00:00-05:00"
END = "2026-09-21T09:00:00-05:00"


@pytest.fixture(autouse=True)
def _stub_services(monkeypatch):
    """Replace the live City clients with canned VERIFIED-clear evidence."""
    evidence_store.reset()
    monkeypatch.setattr(
        handlers, "get_residential_zone_evidence",
        lambda loc: ResidentialZoneEvidence(status=EvidenceStatus.VERIFIED, zone_required=None),
    )
    monkeypatch.setattr(
        handlers, "get_street_cleaning_evidence",
        lambda loc, s, e: StreetCleaningEvidence(status=EvidenceStatus.VERIFIED, windows=[]),
    )
    monkeypatch.setattr(
        handlers, "get_street_closure_evidence",
        lambda loc, s, e: TemporaryClosureEvidence(status=EvidenceStatus.VERIFIED, closures=[]),
    )
    yield
    evidence_store.reset()


def _evaluate(run_id, permit_zone=None):
    return handlers.evaluate_parking_request(run_id, LOC, START, END, permit_zone)


def test_all_evidence_gathered_then_legal():
    run = "r-all"
    handlers.get_residential_restrictions(run, LOC)
    handlers.get_street_cleaning_restrictions(run, LOC, START, END)
    handlers.get_temporary_closures(run, LOC, START, END)

    out = _evaluate(run)
    assert out["decision"]["status"] == "LEGAL"
    assert out["completeness"]["complete"] is True
    # start/end display strings are computed deterministically by the backend
    assert out["decision"]["start_time_display"] == "Sunday, September 20, 2026 at 7:00 PM"
    assert out["decision"]["end_time_display"] == "Monday, September 21, 2026 at 9:00 AM"


def test_skipping_street_cleaning_yields_unknown():
    run = "r-skip-cleaning"
    handlers.get_residential_restrictions(run, LOC)
    # street cleaning tool intentionally NOT called
    handlers.get_temporary_closures(run, LOC, START, END)

    out = _evaluate(run)
    assert out["decision"]["status"] == "UNKNOWN"
    assert out["completeness"]["complete"] is False
    assert any("street_cleaning" in m for m in out["completeness"]["missing"])
    assert not any("residential" in m for m in out["completeness"]["missing"])


def test_skipping_every_evidence_tool_yields_unknown():
    out = _evaluate("r-empty")
    assert out["decision"]["status"] == "UNKNOWN"
    categories = {m.split(":")[0] for m in out["completeness"]["missing"]}
    assert {"residential", "street_cleaning", "temporary_closure"} <= categories


def test_evidence_gathered_for_other_block_does_not_count():
    run = "r-wrong-block"
    handlers.get_residential_restrictions(run, "george-3200w-north")
    handlers.get_street_cleaning_restrictions(run, "george-3200w-north", START, END)
    handlers.get_temporary_closures(run, "george-3200w-north", START, END)

    out = _evaluate(run)  # evaluates LOC, not george-*
    assert out["decision"]["status"] == "UNKNOWN"
    assert out["completeness"]["complete"] is False


def test_unavailable_evidence_is_stored_and_forces_unknown(monkeypatch):
    monkeypatch.setattr(
        handlers, "get_street_cleaning_evidence",
        lambda loc, s, e: StreetCleaningEvidence(
            status=EvidenceStatus.UNAVAILABLE, notes=["portal 503"]
        ),
    )
    run = "r-unavailable"
    handlers.get_residential_restrictions(run, LOC)
    handlers.get_street_cleaning_restrictions(run, LOC, START, END)
    handlers.get_temporary_closures(run, LOC, START, END)

    out = _evaluate(run)
    assert out["decision"]["status"] == "UNKNOWN"
    assert any("UNAVAILABLE" in m for m in out["completeness"]["missing"])


def test_blocker_still_wins_over_incomplete_evidence(monkeypatch):
    monkeypatch.setattr(
        handlers, "get_residential_zone_evidence",
        lambda loc: ResidentialZoneEvidence(status=EvidenceStatus.VERIFIED, zone_required="1439"),
    )
    run = "r-blocked-incomplete"
    handlers.get_residential_restrictions(run, LOC)  # zone 1439 required, no permit
    # street cleaning + closures intentionally skipped

    out = _evaluate(run, permit_zone=None)
    assert out["decision"]["status"] == "NOT_LEGAL"


def test_permit_zone_none_string_is_treated_as_no_permit():
    run = "r-none"
    handlers.get_residential_restrictions(run, LOC)
    handlers.get_street_cleaning_restrictions(run, LOC, START, END)
    handlers.get_temporary_closures(run, LOC, START, END)

    out = _evaluate(run, permit_zone="none")
    assert "error" not in out
    assert out["decision"]["status"] == "LEGAL"
