from datetime import datetime

from app.config import CHICAGO_TZ
from app.locations.registry import get_location
from app.models.evidence import EvidenceStatus
from app.rules.nearby import find_legal_parking_nearby
from app.services.events import get_nearby_events
from app.services.snow_routes import get_snow_route_evidence, in_overnight_ban_period
from tests.conftest import FakeSocrataClient

WINTER = datetime(2026, 1, 20, 19, tzinfo=CHICAGO_TZ)
WINTER_END = datetime(2026, 1, 21, 9, tzinfo=CHICAGO_TZ)
SUMMER = datetime(2026, 7, 4, 12, tzinfo=CHICAGO_TZ)


# --- season calendar ---------------------------------------------------

def test_overnight_ban_period_calendar():
    assert in_overnight_ban_period(WINTER) is True
    assert in_overnight_ban_period(datetime(2026, 4, 1, 3, tzinfo=CHICAGO_TZ)) is True
    assert in_overnight_ban_period(datetime(2026, 4, 2, 3, tzinfo=CHICAGO_TZ)) is False
    assert in_overnight_ban_period(SUMMER) is False


# --- snow routes -----------------------------------------------------

def test_snow_route_match_flags_two_inch_route():
    rows = [{"on_street": "W WRIGHTWOOD AVE", "from_stree": "N X", "to_street": "N Y"}]
    loc = get_location("wrightwood-3300w-north")
    ev = get_snow_route_evidence(loc, WINTER, WINTER_END, client=FakeSocrataClient(rows=rows))
    assert ev.status is EvidenceStatus.VERIFIED
    assert ev.is_two_inch_route is True
    assert ev.in_overnight_ban_period is True
    assert ev.ban_active is False  # only the engine + weather can set this


def test_snow_route_no_match_is_verified_not_a_route():
    loc = get_location("wrightwood-3300w-north")
    ev = get_snow_route_evidence(loc, WINTER, WINTER_END, client=FakeSocrataClient(rows=[]))
    assert ev.status is EvidenceStatus.VERIFIED
    assert ev.is_two_inch_route is False


def test_snow_route_api_failure_is_unavailable():
    loc = get_location("wrightwood-3300w-north")
    ev = get_snow_route_evidence(loc, WINTER, WINTER_END, client=FakeSocrataClient(error="503"))
    assert ev.status is EvidenceStatus.UNAVAILABLE


# --- nearby events -------------------------------------------------

def test_nearby_events_filters_by_distance():
    loc = get_location("wrightwood-3300w-north")  # ~41.9289, -87.7133
    rows = [
        {  # ~200 m away
            "applicationnumber": "DOT1", "worktypedescription": "Festival",
            "comments": "Logan Sq Arts Fest", "latitude": "41.9295", "longitude": "-87.7140",
            "applicationstartdate": "2026-07-03T00:00:00.000",
            "applicationenddate": "2026-07-06T23:59:59.000",
        },
        {  # far away (downtown)
            "applicationnumber": "DOT2", "worktypedescription": "Parade",
            "comments": "Loop parade", "latitude": "41.8830", "longitude": "-87.6290",
            "applicationstartdate": "2026-07-03T00:00:00.000",
            "applicationenddate": "2026-07-06T23:59:59.000",
        },
    ]
    ev = get_nearby_events(
        loc, SUMMER, datetime(2026, 7, 5, 12, tzinfo=CHICAGO_TZ),
        client=FakeSocrataClient(rows=rows),
    )
    assert ev.status is EvidenceStatus.VERIFIED
    assert [e.permit_number for e in ev.events] == ["DOT1"]


def test_nearby_events_api_failure_is_unavailable():
    loc = get_location("wrightwood-3300w-north")
    ev = get_nearby_events(loc, SUMMER, SUMMER, client=FakeSocrataClient(error="boom"))
    assert ev.status is EvidenceStatus.UNAVAILABLE


# --- find_legal_parking_nearby -----------------------------------

def test_find_legal_parking_nearby_excludes_origin_and_respects_radius(monkeypatch):
    import app.rules.gather as g
    import app.rules.nearby as nb
    from app.models.evidence import (
        ParkingEvidence,
        ResidentialZoneEvidence,
        StreetCleaningEvidence,
        TemporaryClosureEvidence,
    )

    def all_clear(_req):
        return ParkingEvidence(
            residential=ResidentialZoneEvidence(status=EvidenceStatus.VERIFIED),
            street_cleaning=StreetCleaningEvidence(status=EvidenceStatus.VERIFIED),
            temporary_closure=TemporaryClosureEvidence(status=EvidenceStatus.VERIFIED),
        )

    monkeypatch.setattr(nb, "gather_evidence", all_clear)
    monkeypatch.setattr(g, "gather_evidence", all_clear)

    out = find_legal_parking_nearby("wrightwood-3300w-north", SUMMER,
                                    datetime(2026, 7, 5, 9, tzinfo=CHICAGO_TZ), None)
    ids = {o.location_id for o in out}
    assert "wrightwood-3300w-north" not in ids
    assert all(o.status in ("LEGAL", "LEGAL_UNTIL") for o in out)
