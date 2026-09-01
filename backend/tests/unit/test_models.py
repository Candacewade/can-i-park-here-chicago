from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.config import CHICAGO_TZ
from app.models.requests import ParkingRequest


def _req(**kw):
    base = dict(
        location_id="x",
        start_time=datetime(2026, 9, 8, 19, tzinfo=CHICAGO_TZ),
        end_time=datetime(2026, 9, 9, 9, tzinfo=CHICAGO_TZ),
    )
    base.update(kw)
    return ParkingRequest(**base)


def test_end_must_be_after_start():
    with pytest.raises(ValidationError):
        _req(end_time=datetime(2026, 9, 8, 18, tzinfo=CHICAGO_TZ))


def test_naive_datetime_is_localized_to_chicago():
    r = _req(start_time=datetime(2026, 9, 8, 19), end_time=datetime(2026, 9, 9, 9))
    assert r.start_time.tzinfo is not None
    assert r.start_time.utcoffset() == timedelta(hours=-5)


@pytest.mark.parametrize(
    "zone,expected",
    [("143", "143"), (" 143 ", "143"), ("1810", "1810"), ("", None),
     ("none", None), ("None", None), ("N/A", None)],
)
def test_permit_zone_normalization(zone, expected):
    assert _req(permit_zone=zone).permit_zone == expected


def test_bad_permit_zone_rejected():
    with pytest.raises(ValidationError):
        _req(permit_zone="not-a-zone")
