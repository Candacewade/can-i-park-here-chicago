from datetime import datetime

from app.config import CHICAGO_TZ
from app.locations.registry import get_location
from app.models.evidence import EvidenceStatus
from app.services.residential_zones import get_residential_zone_evidence
from app.services.street_cleaning import get_street_cleaning_evidence
from tests.conftest import FakeSocrataClient

LOC = get_location("wrightwood-3300w-north")  # zone data: even side, 3300-3320, dir W


# --- residential zones ---------------------------------------------------

def _zone_row(**kw):
    row = dict(
        street_name="WRIGHTWOOD", street_direction="W", street_type="AVE",
        address_range_low="3300", address_range_high="3320", odd_even="E",
        zone="100", buffer="N", status="ACTIVE",
    )
    row.update(kw)
    return row


def test_residential_verified_zone_match():
    ev = get_residential_zone_evidence(LOC, client=FakeSocrataClient(rows=[_zone_row()]))
    assert ev.status is EvidenceStatus.VERIFIED
    assert ev.zone_required == "100"
    assert ev.is_buffer is False


def test_residential_no_segment_is_verified_unrestricted():
    ev = get_residential_zone_evidence(LOC, client=FakeSocrataClient(rows=[]))
    assert ev.status is EvidenceStatus.VERIFIED
    assert ev.zone_required is None


def test_residential_wrong_parity_does_not_match():
    client = FakeSocrataClient(rows=[_zone_row(odd_even="O")])
    ev = get_residential_zone_evidence(LOC, client=client)
    assert ev.zone_required is None


def test_residential_api_failure_is_unavailable_not_unrestricted():
    ev = get_residential_zone_evidence(LOC, client=FakeSocrataClient(error="boom 500"))
    assert ev.status is EvidenceStatus.UNAVAILABLE
    assert ev.zone_required is None


# --- street cleaning ---------------------------------------------------

def _sweep_row(**kw):
    row = {"ward": "35", "section": "09", "september": "8,9"}
    row.update(kw)
    return row


def test_cleaning_window_overlapping_interval():
    start = datetime(2026, 9, 8, 19, tzinfo=CHICAGO_TZ)
    end = datetime(2026, 9, 9, 11, tzinfo=CHICAGO_TZ)
    ev = get_street_cleaning_evidence(
        LOC, start, end, client=FakeSocrataClient(rows=[_sweep_row()])
    )
    assert ev.status is EvidenceStatus.VERIFIED
    assert len(ev.windows) == 1
    assert ev.windows[0].start.hour == 9


def test_cleaning_no_overlap_is_verified_empty():
    start = datetime(2026, 9, 8, 19, tzinfo=CHICAGO_TZ)
    end = datetime(2026, 9, 9, 11, tzinfo=CHICAGO_TZ)
    ev = get_street_cleaning_evidence(
        LOC, start, end, client=FakeSocrataClient(rows=[_sweep_row(september="1")])
    )
    assert ev.status is EvidenceStatus.VERIFIED
    assert ev.windows == []


def test_cleaning_api_failure_is_unavailable():
    start = datetime(2026, 9, 8, 19, tzinfo=CHICAGO_TZ)
    end = datetime(2026, 9, 9, 11, tzinfo=CHICAGO_TZ)
    ev = get_street_cleaning_evidence(LOC, start, end, client=FakeSocrataClient(error="timeout"))
    assert ev.status is EvidenceStatus.UNAVAILABLE


def test_cleaning_unsupported_when_no_zone_and_no_coords():
    loc = LOC.model_copy(update={
        "street_sweeping_ward": None, "street_sweeping_section": None,
        "latitude": None, "longitude": None,
    })
    start = datetime(2026, 9, 8, 19, tzinfo=CHICAGO_TZ)
    end = datetime(2026, 9, 9, 11, tzinfo=CHICAGO_TZ)
    ev = get_street_cleaning_evidence(loc, start, end, client=FakeSocrataClient(rows=[]))
    assert ev.status is EvidenceStatus.UNSUPPORTED


def test_cleaning_falls_back_to_spatial_query_without_zone():
    loc = LOC.model_copy(update={"street_sweeping_ward": None, "street_sweeping_section": None})
    start = datetime(2026, 9, 8, 19, tzinfo=CHICAGO_TZ)
    end = datetime(2026, 9, 9, 11, tzinfo=CHICAGO_TZ)
    client = FakeSocrataClient(rows=[_sweep_row(ward="43", section="03", september="8,9")])
    ev = get_street_cleaning_evidence(loc, start, end, client=client)
    assert ev.status is EvidenceStatus.VERIFIED
    assert ev.ward == "43"
    assert len(ev.windows) == 1
