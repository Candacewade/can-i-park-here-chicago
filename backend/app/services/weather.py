"""Snow / precipitation outlook for a block, from the US National Weather Service.

`api.weather.gov` is free and needs no key (just a descriptive User-Agent). This
is a *forecast*: it feeds the agent's risk narrative, and only firms up the
snow_route verdict when it confirms >=2 inches over the requested interval.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from app.config import CHICAGO_TZ, NWS_API_BASE, NWS_USER_AGENT, SOCRATA_TIMEOUT_SECONDS
from app.models.evidence import EvidenceStatus, SourceProvenance, WeatherOutlookEvidence

_MM_PER_INCH = 25.4
_HEADERS = {"User-Agent": NWS_USER_AGENT, "Accept": "application/geo+json"}


class WeatherError(RuntimeError):
    pass


def _get(url: str) -> dict:
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=SOCRATA_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise WeatherError(f"network error: {exc}") from exc
    if resp.status_code >= 400:
        raise WeatherError(f"NWS returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise WeatherError("non-JSON response from NWS") from exc


def _parse_valid_time(vt: str) -> tuple[datetime, datetime]:
    """NWS validTime is 'ISO8601/ISO8601duration', e.g. '2026-01-05T00:00:00+00:00/PT6H'."""
    start_s, _, dur_s = vt.partition("/")
    start = datetime.fromisoformat(start_s)
    hours = 0.0
    minutes = 0.0
    num = ""
    for ch in dur_s.removeprefix("PT").removeprefix("P"):
        if ch.isdigit():
            num += ch
        elif ch == "H":
            hours = float(num or 0)
            num = ""
        elif ch == "M":
            minutes = float(num or 0)
            num = ""
        elif ch == "D":
            hours += 24 * float(num or 0)
            num = ""
        else:
            num = ""
    return start, start + timedelta(hours=hours, minutes=minutes)


def _overlaps(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    return a0 < b1 and a1 > b0


def get_weather_outlook(
    latitude: float | None,
    longitude: float | None,
    interval_start: datetime,
    interval_end: datetime,
) -> WeatherOutlookEvidence:
    provenance = SourceProvenance(
        source_name="US National Weather Service (api.weather.gov)",
        source_dataset_id="nws-gridpoints",
        retrieved_at=datetime.now(tz=CHICAGO_TZ),
        query=f"{NWS_API_BASE}/points/{latitude},{longitude}",
    )
    if latitude is None or longitude is None:
        return WeatherOutlookEvidence(
            status=EvidenceStatus.UNSUPPORTED,
            provenance=provenance,
            notes=["No coordinates for this block; cannot fetch a forecast."],
        )

    try:
        point = _get(f"{NWS_API_BASE}/points/{latitude:.4f},{longitude:.4f}")
        grid_url = point["properties"]["forecastGridData"]
        grid = _get(grid_url)
        props = grid["properties"]
    except (WeatherError, KeyError) as exc:
        return WeatherOutlookEvidence(
            status=EvidenceStatus.UNAVAILABLE,
            provenance=provenance,
            notes=[f"Could not verify the forecast: {exc}"],
        )

    start = interval_start.astimezone(CHICAGO_TZ)
    end = interval_end.astimezone(CHICAGO_TZ)

    snow_mm = 0.0
    for entry in props.get("snowfallAmount", {}).get("values", []):
        try:
            e0, e1 = _parse_valid_time(entry["validTime"])
        except (KeyError, ValueError):
            continue
        if entry.get("value") and _overlaps(e0, e1, start, end):
            snow_mm += float(entry["value"])

    max_prob: int | None = None
    for entry in props.get("probabilityOfPrecipitation", {}).get("values", []):
        try:
            e0, e1 = _parse_valid_time(entry["validTime"])
        except (KeyError, ValueError):
            continue
        if entry.get("value") is not None and _overlaps(e0, e1, start, end):
            max_prob = max(max_prob or 0, int(entry["value"]))

    snow_in = round(snow_mm / _MM_PER_INCH, 1)
    if snow_in >= 0.1:
        summary = f"About {snow_in} in of snow expected during the interval"
    elif max_prob and max_prob >= 30:
        summary = f"Precipitation likely ({max_prob}% chance), little or no snow"
    else:
        summary = "No significant snow expected during the interval"

    return WeatherOutlookEvidence(
        status=EvidenceStatus.VERIFIED,
        provenance=provenance,
        expected_snow_inches=snow_in,
        max_snow_probability=max_prob,
        summary=summary,
    )
