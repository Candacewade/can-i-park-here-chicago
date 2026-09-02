from datetime import datetime, timedelta

import pytest

from app import evidence_store
from app.config import CHICAGO_TZ
from app.models.evidence import EvidenceStatus, WeatherOutlookEvidence

START = datetime(2026, 1, 8, 19, tzinfo=CHICAGO_TZ)
END = datetime(2026, 1, 9, 11, tzinfo=CHICAGO_TZ)


@pytest.fixture(autouse=True)
def _clean_store():
    evidence_store.reset()
    yield
    evidence_store.reset()


def _weather(inches):
    return WeatherOutlookEvidence(status=EvidenceStatus.VERIFIED, expected_snow_inches=inches)


def test_record_then_read_back_verdict_relevant():
    evidence_store.record(
        "run1", evidence_store.WEATHER,
        location_id="loc", evidence=_weather(3.0), start=START, end=END,
    )
    got = evidence_store.verdict_relevant_evidence(
        "run1", location_id="loc", start=START, end=END
    )
    assert got[evidence_store.WEATHER].expected_snow_inches == 3.0


def test_unknown_run_id_is_empty():
    assert evidence_store.verdict_relevant_evidence(
        "nope", location_id="loc", start=START, end=END
    ) == {}


def test_evidence_for_different_block_is_not_returned():
    evidence_store.record(
        "run1", evidence_store.WEATHER,
        location_id="block-A", evidence=_weather(3.0), start=START, end=END,
    )
    got = evidence_store.verdict_relevant_evidence(
        "run1", location_id="block-B", start=START, end=END
    )
    assert got == {}


def test_evidence_for_different_interval_is_not_returned():
    evidence_store.record(
        "run1", evidence_store.WEATHER,
        location_id="loc", evidence=_weather(3.0), start=START, end=END,
    )
    got = evidence_store.verdict_relevant_evidence(
        "run1", location_id="loc", start=START, end=END + timedelta(hours=3)
    )
    assert got == {}


def test_equivalent_timestamps_different_offset_still_match():
    evidence_store.record(
        "run1", evidence_store.EVENTS,
        location_id="loc", evidence=_weather(0.0), start=START, end=END,
    )
    got = evidence_store.verdict_relevant_evidence(
        "run1", location_id="loc", start=START.astimezone(), end=END.astimezone()
    )
    assert evidence_store.EVENTS in got


def test_closure_detail_is_not_verdict_relevant():
    evidence_store.record(
        "run1", evidence_store.CLOSURE_DETAIL,
        location_id="loc", evidence=_weather(0.0), start=START, end=END,
    )
    got = evidence_store.verdict_relevant_evidence(
        "run1", location_id="loc", start=START, end=END
    )
    assert got == {}  # stored for tracing, never fed to the engine


def test_clear_and_reset():
    evidence_store.record(
        "run1", evidence_store.WEATHER,
        location_id="loc", evidence=_weather(1.0), start=START, end=END,
    )
    evidence_store.clear("run1")
    assert evidence_store.verdict_relevant_evidence(
        "run1", location_id="loc", start=START, end=END
    ) == {}
