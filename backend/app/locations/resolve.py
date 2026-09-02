"""Resolve a Chicago street address to a canonical ``ChicagoParkingLocation``.

    address + ZIP
      -> US Census geocoder (point, normalized street parts, block range, side)
      -> in-Chicago gate (City Boundary)
      -> canonical segment (Chicago Street Center Lines)
      -> side N/S/E/W  (geometry cross-product + parity convention; UI confirms)
      -> cross streets (segment endpoint topology)
      -> sweeping ward/section  (Street Sweeping Zones, point-in-polygon)
      -> neighborhood            (Community Areas, point-in-polygon; display only)
      -> ChicagoParkingLocation per candidate side, cached in blocks.json

See docs/location-model.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import (
    DATASET_CITY_BOUNDARY,
    DATASET_COMMUNITY_AREAS,
    DATASET_STREET_CENTERLINES,
    DATASET_STREET_SWEEPING_ZONES,
)
from app.geo import dominant_axis, line_centroid, line_endpoints, signed_side
from app.locations.geocode import GeocodeError, GeocodeResult, census_geocode
from app.locations.registry import ChicagoParkingLocation, side_from_slug, slug_for_street
from app.services.socrata import SocrataClient, SocrataError

_DIRECTIONS = {"N", "S", "E", "W"}
_NS_SIDES = ("east", "west")
_EW_SIDES = ("north", "south")


@dataclass
class ResolvedLocation:
    query: str
    in_chicago: bool
    matched_address: str | None = None
    neighborhood: str | None = None
    suggested_side: str | None = None
    side_options: list[str] = field(default_factory=list)
    side_confidence: str = "low"          # user | high | low
    locations: dict[str, ChicagoParkingLocation] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def suggested(self) -> ChicagoParkingLocation | None:
        return self.locations.get(self.suggested_side or "")


def _q(value: str) -> str:
    return value.replace("'", "''")


def _point_hits(
    client: SocrataClient, dataset: str, lon: float, lat: float, select: str
) -> dict | None:
    params = {
        "$where": f"intersects(the_geom,'POINT({lon} {lat})')",
        "$select": select,
        "$limit": "1",
    }
    try:
        rows = client.get_rows(dataset, params)
    except SocrataError:
        return None
    return rows[0] if rows else None


def _find_segment(
    client: SocrataClient, street: str, pre_dir: str, number: int
) -> dict | None:
    where = f"street_nam='{_q(street)}'"
    if pre_dir:
        where += f" AND pre_dir='{_q(pre_dir)}'"
    params = {"$where": where, "$limit": "200"}
    try:
        rows = client.get_rows(DATASET_STREET_CENTERLINES, params)
    except SocrataError:
        return None

    def _rng(row: dict, a: str, b: str) -> tuple[int, int] | None:
        try:
            lo, hi = int(float(row[a])), int(float(row[b]))
        except (KeyError, TypeError, ValueError):
            return None
        return (min(lo, hi), max(lo, hi)) if (lo or hi) else None

    for row in rows:
        for a, b in (("l_f_add", "l_t_add"), ("r_f_add", "r_t_add")):
            rng = _rng(row, a, b)
            if rng and rng[0] <= number <= rng[1]:
                return row
    return None


def _matched_range(row: dict, number: int) -> tuple[int, int, str]:
    """Return (low, high, tiger_side 'L'/'R') for the range that contains ``number``."""
    for a, b, side in (("l_f_add", "l_t_add", "L"), ("r_f_add", "r_t_add", "R")):
        try:
            lo, hi = int(float(row[a])), int(float(row[b]))
        except (KeyError, TypeError, ValueError):
            continue
        lo, hi = min(lo, hi), max(lo, hi)
        if lo <= number <= hi:
            return lo, hi, side
    return number, number, "L"


def _geometry_side(geom: dict, lon: float | None, lat: float | None, number: int) -> str | None:
    if lon is None or lat is None or not geom:
        return None
    try:
        start, end = line_endpoints(geom)
    except (IndexError, KeyError, TypeError):
        return None
    s = signed_side(start, end, (lon, lat))
    if abs(s) < 1e-12:
        return None
    left = s > 0
    dnorth = end[1] - start[1]
    deast = end[0] - start[0]
    if abs(dnorth) >= abs(deast):           # travelling mostly N or S
        northbound = dnorth > 0
        if northbound:
            return "west" if left else "east"
        return "east" if left else "west"
    eastbound = deast > 0                    # travelling mostly E or W
    if eastbound:
        return "north" if left else "south"
    return "south" if left else "north"


def _convention_side(axis: str, number: int) -> str:
    even = number % 2 == 0
    if axis == "ns":
        return "west" if even else "east"       # Chicago grid: even = W/S, odd = E/N
    return "south" if even else "north"


def _cross_streets(client: SocrataClient, row: dict, street: str) -> tuple[str | None, str | None]:
    fnode, tnode = row.get("fnode_id"), row.get("tnode_id")
    nodes = [n for n in (fnode, tnode) if n]
    if not nodes:
        return None, None
    ids = ",".join(f"'{_q(str(n))}'" for n in nodes)
    params = {
        "$where": f"(fnode_id in ({ids}) OR tnode_id in ({ids})) AND street_nam!='{_q(street)}'",
        "$select": "street_nam,street_typ,pre_dir,fnode_id,tnode_id",
        "$limit": "40",
    }
    try:
        rows = client.get_rows(DATASET_STREET_CENTERLINES, params)
    except SocrataError:
        return None, None

    def _name_at(node) -> str | None:
        for r in rows:
            if str(r.get("fnode_id")) == str(node) or str(r.get("tnode_id")) == str(node):
                return _display_street(
                    (r.get("pre_dir") or "").upper(),
                    r.get("street_nam") or "",
                    r.get("street_typ") or "",
                )
        return None

    return _name_at(fnode), _name_at(tnode)


def _display_street(pre_dir: str, name: str, suffix: str) -> str:
    parts = [pre_dir.upper(), name.title(), suffix.title()]
    return " ".join(p for p in parts if p).strip()


def _location_id(pre_dir: str, name: str, suffix: str, block_low: int, side: str) -> str:
    return f"{slug_for_street(pre_dir, name, suffix)}-{block_low}-{side}"


def resolve_address(
    number: int,
    street: str,
    zip_code: str = "",
    side: str | None = None,
    client: SocrataClient | None = None,
) -> ResolvedLocation:
    client = client or SocrataClient()
    query = f"{number} {street} {zip_code}".strip()
    result = ResolvedLocation(query=query, in_chicago=False)

    # 1. geocode (Census) -- fall back to centerline-only on failure
    geo: GeocodeResult | None = None
    try:
        geo = census_geocode(number, street, zip_code)
    except GeocodeError as exc:
        result.notes.append(f"Census geocoder unavailable ({exc}); using street data only.")

    street_name = geo.street_name if geo else _strip_dir_suffix(street)[1]
    pre_dir = geo.pre_direction if geo else _strip_dir_suffix(street)[0]
    suffix = geo.suffix_type if geo else _strip_dir_suffix(street)[2]
    lat = geo.latitude if geo else None
    lon = geo.longitude if geo else None
    result.matched_address = geo.matched_address if geo else None

    # 3. canonical segment
    row = _find_segment(client, street_name, pre_dir, number)
    if row is None:
        result.notes.append("No Chicago street-centerline segment matched this address.")
        return result

    geom = row.get("the_geom") or {}
    if lat is None or lon is None:
        lon, lat = line_centroid(geom) if geom else (None, None)

    # 2. in-Chicago gate
    if lat is not None and lon is not None:
        boundary = _point_hits(client, DATASET_CITY_BOUNDARY, lon, lat, "name")
        result.in_chicago = boundary is not None
        if not result.in_chicago:
            result.notes.append("This address is outside the City of Chicago boundary.")
            return result
    else:
        result.in_chicago = True  # a centerline match implies Chicago

    block_low, block_high, _tiger = _matched_range(row, number)

    # 4. side
    try:
        start, end = line_endpoints(geom)
        axis = dominant_axis(start, end)
    except (IndexError, KeyError, TypeError):
        axis = "ns"
    options = list(_NS_SIDES if axis == "ns" else _EW_SIDES)
    geom_side = _geometry_side(geom, lon, lat, number)
    conv_side = _convention_side(axis, number)

    if side and side.lower() in options:
        result.suggested_side, result.side_confidence = side.lower(), "user"
    elif geom_side and geom_side == conv_side:
        result.suggested_side, result.side_confidence = geom_side, "high"
    elif geom_side:
        result.suggested_side, result.side_confidence = geom_side, "low"
        result.notes.append(
            "Geometry and the odd/even convention disagree on the side; please confirm."
        )
    else:
        result.suggested_side, result.side_confidence = conv_side, "low"
    result.side_options = options

    # 5-7. cross streets, sweeping zone, neighborhood
    from_x, to_x = _cross_streets(client, row, street_name)
    ward = section = None
    if lat is not None and lon is not None:
        sz = _point_hits(client, DATASET_STREET_SWEEPING_ZONES, lon, lat, "ward,section")
        if sz:
            ward, section = sz.get("ward"), sz.get("section")
        ca = _point_hits(client, DATASET_COMMUNITY_AREAS, lon, lat, "community")
        if ca and ca.get("community"):
            result.neighborhood = ca["community"].title()

    parity = "even" if number % 2 == 0 else "odd"
    display = _display_street(pre_dir, street_name, suffix)

    # 8. one ChicagoParkingLocation per candidate side
    for opt in options:
        loc = ChicagoParkingLocation(
            location_id=_location_id(pre_dir, street_name, suffix, block_low, opt),
            neighborhood=result.neighborhood or "Chicago",
            street_name=display,
            from_cross_street=from_x or "the previous cross street",
            to_cross_street=to_x or "the next cross street",
            side=opt,
            address_parity=parity,
            address_number=number,
            zip_code=geo.zip_code if geo else (zip_code or None),
            address_range_low=block_low,
            address_range_high=block_high,
            street_sweeping_ward=ward,
            street_sweeping_section=section,
            latitude=lat,
            longitude=lon,
        )
        result.locations[opt] = loc

    return result


def _strip_dir_suffix(street: str) -> tuple[str, str, str]:
    """Best-effort parse of 'N Clark St' -> ('N', 'CLARK', 'ST') without a geocoder."""
    tokens = re.split(r"\s+", street.strip().upper())
    pre = tokens.pop(0) if tokens and tokens[0] in _DIRECTIONS else ""
    suffix = tokens.pop() if len(tokens) > 1 else ""
    return pre, " ".join(tokens), suffix


def resolve_location_id(
    location_id: str, client: SocrataClient | None = None
) -> ChicagoParkingLocation | None:
    """Reconstruct a ChicagoParkingLocation from its id alone (for get_location on a
    cache miss). Synthesizes a representative address and re-resolves."""
    parsed = side_from_slug(location_id)
    if parsed is None:
        return None
    pre_dir, name, suffix, block_low, side = parsed
    display_street = _display_street(pre_dir, name, suffix)
    rep_number = block_low + (1 if side in ("north", "east") else 0)
    resolved = resolve_address(rep_number, display_street, "", side=side, client=client)
    return resolved.locations.get(side)
