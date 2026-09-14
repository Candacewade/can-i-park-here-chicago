"""Reverse geocode: browser coordinates -> a plausible Chicago street address.

    (lat, lon)
      -> nearest Chicago Street Center Line segment (pr57-gg9e -- the SAME
         dataset resolve_address() already queries; a spatial within_circle
         search this time instead of a name+number match)
      -> which side of that segment the point falls on (existing signed_side)
      -> an ESTIMATED house number, interpolated along that side's address
         range at the point's projected position along the segment
      -> handed to the existing resolve_address() pipeline, which re-verifies
         everything from scratch (city boundary, side, cross streets,
         sweeping zone, neighborhood) exactly as it would for a typed address

This module's only job is producing a plausible (number, street) starting
point -- it never bypasses resolve_address()'s own verification, and the
frontend always shows the normal block/side CONFIRMATION step before
anything runs. Zero new external services: the Street Center Lines dataset is
already part of this app's approved, official-City-data stack.
"""

from __future__ import annotations

from app.config import DATASET_STREET_CENTERLINES
from app.geo import haversine_km, line_endpoints, nearest_point_on_segment, signed_side
from app.locations.resolve import ResolvedLocation, _display_street, resolve_address
from app.services.socrata import SocrataClient, SocrataError

_SEARCH_RADIUS_METERS = 150


def _nearby_segments(client: SocrataClient, lon: float, lat: float) -> list[dict]:
    params = {
        "$where": f"within_circle(the_geom, {lat}, {lon}, {_SEARCH_RADIUS_METERS})",
        "$limit": "50",
    }
    try:
        return client.get_rows(DATASET_STREET_CENTERLINES, params)
    except SocrataError:
        return []


def _int_or_none(row: dict, key: str) -> int | None:
    try:
        return int(float(row[key]))
    except (KeyError, TypeError, ValueError):
        return None


def _address_range(row: dict, left: bool) -> tuple[int, int] | None:
    """The (low, high) address range on the requested side; falls back to the
    other side if that one has no addresses recorded (rare, but seen on some
    Street Center Lines segments)."""
    for want_left in (left, not left):
        a, b = ("l_f_add", "l_t_add") if want_left else ("r_f_add", "r_t_add")
        lo, hi = _int_or_none(row, a), _int_or_none(row, b)
        if lo is not None and hi is not None and (lo or hi):
            return min(lo, hi), max(lo, hi)
    return None


def reverse_geocode(
    lat: float, lon: float, client: SocrataClient | None = None
) -> ResolvedLocation | None:
    """(lat, lon) -> a ResolvedLocation, the same shape a typed-address lookup
    produces (side options, cross streets, the whole pipeline). None if no
    Chicago street segment is near enough to guess from."""
    client = client or SocrataClient()
    rows = _nearby_segments(client, lon, lat)

    best_row = best_start = best_end = None
    best_t = 0.0
    best_dist_km = float("inf")
    for row in rows:
        geom = row.get("the_geom") or {}
        try:
            start, end = line_endpoints(geom)
        except (IndexError, KeyError, TypeError):
            continue
        projected, t = nearest_point_on_segment(start, end, (lon, lat))
        dist_km = haversine_km(lat, lon, projected[1], projected[0])
        if dist_km < best_dist_km:
            best_row, best_start, best_end, best_t, best_dist_km = row, start, end, t, dist_km

    if best_row is None or best_start is None or best_end is None:
        return None

    left = signed_side(best_start, best_end, (lon, lat)) > 0
    address_range = _address_range(best_row, left)
    if address_range is None:
        return None
    lo, hi = address_range
    estimated_number = round(lo + best_t * (hi - lo)) or (lo or hi)
    if estimated_number <= 0:
        return None

    street = _display_street(
        (best_row.get("pre_dir") or "").upper(),
        best_row.get("street_nam") or "",
        best_row.get("street_typ") or "",
    )
    if not street:
        return None

    return resolve_address(estimated_number, street, "", client=client)
