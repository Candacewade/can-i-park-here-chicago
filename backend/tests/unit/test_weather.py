from datetime import datetime

import httpx
import respx

from app.config import CHICAGO_TZ
from app.models.evidence import EvidenceStatus
from app.services.weather import get_weather_outlook

START = datetime(2026, 1, 20, 18, tzinfo=CHICAGO_TZ)
END = datetime(2026, 1, 21, 12, tzinfo=CHICAGO_TZ)

_POINT = {"properties": {"forecastGridData": "https://api.weather.gov/gridpoints/LOT/70,73"}}


def _grid(snow_mm, prob):
    # one 24h block covering the interval
    vt = "2026-01-20T00:00:00+00:00/PT48H"
    return {
        "properties": {
            "snowfallAmount": {"values": [{"validTime": vt, "value": snow_mm}]},
            "probabilityOfPrecipitation": {"values": [{"validTime": vt, "value": prob}]},
        }
    }


@respx.mock
def test_verified_snow_forecast_in_inches():
    respx.get("https://api.weather.gov/points/41.9289,-87.7133").mock(
        return_value=httpx.Response(200, json=_POINT)
    )
    respx.get("https://api.weather.gov/gridpoints/LOT/70,73").mock(
        return_value=httpx.Response(200, json=_grid(76.2, 90))  # 76.2 mm = 3.0 in
    )
    ev = get_weather_outlook(41.9289, -87.7133, START, END)
    assert ev.status is EvidenceStatus.VERIFIED
    assert ev.expected_snow_inches == 3.0
    assert ev.max_snow_probability == 90


@respx.mock
def test_nws_failure_is_unavailable():
    respx.get("https://api.weather.gov/points/41.9289,-87.7133").mock(
        return_value=httpx.Response(500)
    )
    ev = get_weather_outlook(41.9289, -87.7133, START, END)
    assert ev.status is EvidenceStatus.UNAVAILABLE


def test_missing_coords_is_unsupported():
    ev = get_weather_outlook(None, None, START, END)
    assert ev.status is EvidenceStatus.UNSUPPORTED
