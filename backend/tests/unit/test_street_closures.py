from datetime import datetime

from app.config import CHICAGO_TZ
from app.locations.registry import get_location
from app.models.evidence import EvidenceStatus
from app.services.street_closures import get_street_closure_evidence
from tests.conftest import FakeSocrataClient

LOC = get_location("wrightwood-3300w-north")  # WRIGHTWOOD, dir W, 3300-3320
START = datetime(2026, 9, 9, 7, tzinfo=CHICAGO_TZ)
END = datetime(2026, 9, 9, 20, tzinfo=CHICAGO_TZ)


def _row(**kw):
    row = dict(
        applicationnumber="DOT100", streetname="WRIGHTWOOD", direction="W",
        streetnumberfrom="3300", streetnumberto="3320",
        applicationstartdate="2026-09-08T00:00:00.000",
        applicationenddate="2026-09-10T23:59:59.000",
        applicationstatus="Open", currentmilestone="Inspection",
        streetclosure="Curblane", parkingmeterpostingorbagging="Y",
        worktypedescription="Opening in the Public Way",
    )
    row.update(kw)
    return row


def test_matching_open_curblane_permit_is_returned():
    ev = get_street_closure_evidence(LOC, START, END, client=FakeSocrataClient(rows=[_row()]))
    assert ev.status is EvidenceStatus.VERIFIED
    assert len(ev.closures) == 1
    assert ev.closures[0].blocks_parking is True


def test_closed_permit_ignored():
    ev = get_street_closure_evidence(
        LOC, START, END, client=FakeSocrataClient(rows=[_row(applicationstatus="Closed")])
    )
    assert ev.closures == []


def test_cancelled_milestone_ignored():
    ev = get_street_closure_evidence(
        LOC, START, END, client=FakeSocrataClient(rows=[_row(currentmilestone="Cancelled")])
    )
    assert ev.closures == []


def test_address_range_outside_block_ignored():
    ev = get_street_closure_evidence(
        LOC, START, END,
        client=FakeSocrataClient(rows=[_row(streetnumberfrom="5000", streetnumberto="5050")]),
    )
    assert ev.closures == []


def test_partial_closure_without_meter_flag_not_parking_impact():
    row = _row(streetclosure="Partial", parkingmeterpostingorbagging=None)
    ev = get_street_closure_evidence(LOC, START, END, client=FakeSocrataClient(rows=[row]))
    assert ev.closures == []


def test_garbage_future_date_ignored():
    ev = get_street_closure_evidence(
        LOC, START, END,
        client=FakeSocrataClient(rows=[_row(applicationenddate="2112-09-10T23:59:59.000")]),
    )
    # start 2026-09-08, end 2112 -> _parse_dt rejects the end date -> skipped
    assert ev.closures == []


def test_api_failure_is_unavailable():
    ev = get_street_closure_evidence(LOC, START, END, client=FakeSocrataClient(error="503"))
    assert ev.status is EvidenceStatus.UNAVAILABLE
