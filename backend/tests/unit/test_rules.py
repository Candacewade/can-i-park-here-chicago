"""Deterministic rule engine + completeness check. No network."""

from datetime import datetime

import pytest

from app.config import CHICAGO_TZ
from app.models.decision import ParkingStatus
from app.models.evidence import (
    EvidenceStatus,
    ParkingEvidence,
    ResidentialZoneEvidence,
    StreetCleaningEvidence,
    StreetCleaningWindow,
    TemporaryClosure,
    TemporaryClosureEvidence,
)
from app.models.requests import ParkingRequest
from app.rules.completeness import check_completeness
from app.rules.engine import evaluate_parking

START = datetime(2026, 9, 8, 19, tzinfo=CHICAGO_TZ)
END = datetime(2026, 9, 9, 11, tzinfo=CHICAGO_TZ)


def _req(permit=None):
    return ParkingRequest(location_id="x", start_time=START, end_time=END, permit_zone=permit)


def _res(zone=None, buffer=False, status=EvidenceStatus.VERIFIED):
    return ResidentialZoneEvidence(status=status, zone_required=zone, is_buffer=buffer)


def _clean(windows=None, status=EvidenceStatus.VERIFIED):
    return StreetCleaningEvidence(status=status, windows=windows or [])


def _closure(closures=None, status=EvidenceStatus.VERIFIED):
    return TemporaryClosureEvidence(status=status, closures=closures or [])


def _all_clear_evidence(**over):
    base = dict(residential=_res(), street_cleaning=_clean(), temporary_closure=_closure())
    base.update(over)
    return ParkingEvidence(**base)


def _window(start_h, end_h, day=9):
    s = datetime(2026, 9, day, start_h, tzinfo=CHICAGO_TZ)
    e = datetime(2026, 9, day, end_h, tzinfo=CHICAGO_TZ)
    return StreetCleaningWindow(date=s, start=s, end=e, description="cleaning")


def test_legal_when_all_clear():
    d = evaluate_parking(_req(), _all_clear_evidence())
    assert d.status is ParkingStatus.LEGAL


def test_not_legal_missing_permit():
    d = evaluate_parking(_req(), _all_clear_evidence(residential=_res(zone="143")))
    assert d.status is ParkingStatus.NOT_LEGAL


def test_legal_when_permit_matches():
    d = evaluate_parking(_req(permit="143"), _all_clear_evidence(residential=_res(zone="143")))
    assert d.status is ParkingStatus.LEGAL


def test_buffer_zone_allows_without_permit():
    d = evaluate_parking(_req(), _all_clear_evidence(residential=_res(zone="143", buffer=True)))
    assert d.status is ParkingStatus.LEGAL


def test_legal_until_when_cleaning_starts_mid_interval():
    d = evaluate_parking(_req(), _all_clear_evidence(street_cleaning=_clean([_window(9, 15)])))
    assert d.status is ParkingStatus.LEGAL_UNTIL
    assert d.move_by == datetime(2026, 9, 9, 9, tzinfo=CHICAGO_TZ)


def test_not_legal_when_cleaning_active_at_start():
    req = ParkingRequest(
        location_id="x",
        start_time=datetime(2026, 9, 9, 10, tzinfo=CHICAGO_TZ),
        end_time=datetime(2026, 9, 9, 14, tzinfo=CHICAGO_TZ),
    )
    d = evaluate_parking(req, _all_clear_evidence(street_cleaning=_clean([_window(9, 15)])))
    assert d.status is ParkingStatus.NOT_LEGAL


def test_earliest_limit_wins_move_by():
    ev = _all_clear_evidence(street_cleaning=_clean([_window(10, 15), _window(8, 9, day=9)]))
    d = evaluate_parking(_req(), ev)
    assert d.status is ParkingStatus.LEGAL_UNTIL
    assert d.move_by.hour == 8


def test_unknown_when_required_evidence_unavailable():
    ev = _all_clear_evidence(street_cleaning=_clean(status=EvidenceStatus.UNAVAILABLE))
    d = evaluate_parking(_req(), ev)
    assert d.status is ParkingStatus.UNKNOWN
    assert any("street_cleaning" in u for u in d.unknown_reasons)


def test_unknown_when_category_not_gathered():
    ev = ParkingEvidence(residential=_res(), street_cleaning=_clean())  # no closure
    d = evaluate_parking(_req(), ev)
    assert d.status is ParkingStatus.UNKNOWN


def test_not_legal_beats_unknown():
    # blocked by residential AND cleaning data missing -> still NOT_LEGAL
    ev = ParkingEvidence(
        residential=_res(zone="143"),
        street_cleaning=_clean(status=EvidenceStatus.UNAVAILABLE),
        temporary_closure=_closure(),
    )
    d = evaluate_parking(_req(), ev)
    assert d.status is ParkingStatus.NOT_LEGAL


def test_temporary_closure_blocks():
    c = TemporaryClosure(
        permit_number="DOT1", closure_type="Full", start=START, end=END,
        meter_posting_or_bagging=True, work_description="water main", blocks_parking=True,
    )
    d = evaluate_parking(_req(), _all_clear_evidence(temporary_closure=_closure([c])))
    assert d.status is ParkingStatus.NOT_LEGAL


@pytest.mark.parametrize("status", [EvidenceStatus.UNAVAILABLE, EvidenceStatus.UNSUPPORTED])
def test_completeness_flags_non_verified(status):
    ev = _all_clear_evidence(residential=_res(status=status))
    assert check_completeness(_req(), ev).complete is False
