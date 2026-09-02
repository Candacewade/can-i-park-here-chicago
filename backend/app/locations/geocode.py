"""US Census Bureau geocoder client.

`geocoding.geo.census.gov` -- free, no API key, official TIGER/Line address
ranges. Given a Chicago address it returns the interpolated point (offset to the
correct side of the street), the normalized street parts, the matched segment's
address range, and the TIGER left/right side.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import CENSUS_BENCHMARK, CENSUS_GEOCODER_BASE, SOCRATA_TIMEOUT_SECONDS


class GeocodeError(RuntimeError):
    """The geocoder failed or returned no usable match."""


@dataclass
class GeocodeResult:
    matched_address: str
    latitude: float
    longitude: float
    street_name: str          # e.g. "CLARK"
    pre_direction: str         # e.g. "N" ("" if none)
    suffix_type: str           # e.g. "ST"
    zip_code: str
    block_from: int            # matched segment's low address on the matched side
    block_to: int
    tiger_side: str            # "L" or "R" ("" if unknown)
    tiger_line_id: str | None


def _as_int(v: str | None) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def census_geocode(number: int, street: str, zip_code: str) -> GeocodeResult:
    one_line = f"{number} {street}, Chicago, IL {zip_code}".strip()
    params = {
        "address": one_line,
        "benchmark": CENSUS_BENCHMARK,
        "format": "json",
    }
    url = f"{CENSUS_GEOCODER_BASE}/locations/onelineaddress"
    try:
        resp = httpx.get(url, params=params, timeout=SOCRATA_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise GeocodeError(f"census geocoder unreachable: {exc}") from exc
    if resp.status_code >= 400:
        raise GeocodeError(f"census geocoder HTTP {resp.status_code}")
    try:
        matches = resp.json()["result"]["addressMatches"]
    except (ValueError, KeyError) as exc:
        raise GeocodeError("census geocoder returned an unexpected shape") from exc
    if not matches:
        raise GeocodeError(f"no census match for {one_line!r}")

    m = matches[0]
    coords = m.get("coordinates") or {}
    comp = m.get("addressComponents") or {}
    tiger = m.get("tigerLine") or {}
    lat = coords.get("y")
    lon = coords.get("x")
    if lat is None or lon is None:
        raise GeocodeError("census match had no coordinates")

    return GeocodeResult(
        matched_address=m.get("matchedAddress", one_line),
        latitude=float(lat),
        longitude=float(lon),
        street_name=(comp.get("streetName") or street).strip().upper(),
        pre_direction=(comp.get("preDirection") or "").strip().upper(),
        suffix_type=(comp.get("suffixType") or "").strip().upper(),
        zip_code=(comp.get("zip") or zip_code).strip(),
        block_from=_as_int(comp.get("fromAddress")) or number,
        block_to=_as_int(comp.get("toAddress")) or number,
        tiger_side=(tiger.get("side") or "").strip().upper(),
        tiger_line_id=tiger.get("tigerLineId"),
    )
