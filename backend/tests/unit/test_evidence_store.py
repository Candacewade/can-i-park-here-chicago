from datetime import datetime, timedelta

import pytest

from app import evidence_store
from app.config import CHICAGO_TZ
from app.models.evidence import (
    EvidenceStatus,
    ResidentialZoneEvidence,
    StreetCleaningEvidence,
)

START = datetime(2026, 9, 8, 19, tzinfo=CHICAGO_TZ)
END = datetime(2026, 9, 9, 11, tzinfo=CHICAGO_TZ)


@pytest.fixture(autouse=True)
def _clean_store():
    evidence_store.reset()
    yield
    evidence_store.reset()


def test_record_then_build_bundle_returns_stored_evidence():
    res = ResidentialZoneEvidence(status=EvidenceStatus.VERIFIED, zone_required="143")
    clean = StreetCleaningEvidence(status=EvidenceStatus.VERIFIED)
    evidence_store.record("run1", evidence_store.RESIDENTIAL, location_id="loc", evidence=res)
    evidence_store.record(
        "run1", evidence_store.STREET_CLEANING,
        location_id="loc", evidence=clean, start=START, end=END,
    )

    bundle = evidence_store.build_bundle("run1", location_id="loc", start=START, end=END)
    assert bundle.residential is res
    assert bundle.street_cleaning is clean
    assert bundle.temporary_closure is None  # never recorded


def test_unknown_run_id_yields_empty_bundle():
    bundle = evidence_store.build_bundle("nope", location_id="loc", start=START, end=END)
    assert bundle.residential is None
    assert bundle.street_cleaning is None
    assert bundle.temporary_closure is None


def test_evidence_for_different_block_is_not_returned():
    res = ResidentialZoneEvidence(status=EvidenceStatus.VERIFIED, zone_required="143")
    evidence_store.record("run1", evidence_store.RESIDENTIAL, location_id="block-A", evidence=res)
    bundle = evidence_store.build_bundle("run1", location_id="block-B", start=START, end=END)
    assert bundle.residential is None


def test_street_cleaning_for_different_interval_is_not_returned():
    clean = StreetCleaningEvidence(status=EvidenceStatus.VERIFIED)
    evidence_store.record(
        "run1", evidence_store.STREET_CLEANING,
        location_id="loc", evidence=clean, start=START, end=END,
    )
    other_end = END + timedelta(hours=3)
    bundle = evidence_store.build_bundle("run1", location_id="loc", start=START, end=other_end)
    assert bundle.street_cleaning is None


def test_equivalent_timestamps_with_different_offset_still_match():
    clean = StreetCleaningEvidence(status=EvidenceStatus.VERIFIED)
    evidence_store.record(
        "run1", evidence_store.STREET_CLEANING,
        location_id="loc", evidence=clean, start=START, end=END,
    )
    # same instants, expressed in UTC
    bundle = evidence_store.build_bundle(
        "run1",
        location_id="loc",
        start=START.astimezone(tz=None).astimezone(),
        end=END.astimezone(),
    )
    assert bundle.street_cleaning is clean


def test_clear_removes_run():
    res = ResidentialZoneEvidence(status=EvidenceStatus.VERIFIED)
    evidence_store.record("run1", evidence_store.RESIDENTIAL, location_id="loc", evidence=res)
    evidence_store.clear("run1")
    bundle = evidence_store.build_bundle("run1", location_id="loc", start=START, end=END)
    assert bundle.residential is None
