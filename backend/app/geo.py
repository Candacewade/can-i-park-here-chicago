"""Small geo helpers (no external deps)."""

from __future__ import annotations

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def approx_walk_minutes(km: float) -> int:
    """Rough walking time at ~5 km/h."""
    return max(1, round(km / 5.0 * 60))


# --- point / line / polygon (planar, GeoJSON [lon, lat] order) ---------

Point = tuple[float, float]  # (lon, lat)


def _ring_contains(ring: list[list[float]], lon: float, lat: float) -> bool:
    """Ray-casting point-in-ring test."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def point_in_polygon(geom: dict, lon: float, lat: float) -> bool:
    """True if (lon, lat) is inside a GeoJSON Polygon or MultiPolygon.

    Outer ring contains, minus any holes.
    """
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    polys = coords if gtype == "MultiPolygon" else [coords]
    for poly in polys:
        if not poly:
            continue
        if _ring_contains(poly[0], lon, lat) and not any(
            _ring_contains(hole, lon, lat) for hole in poly[1:]
        ):
            return True
    return False


def _flatten_line(geom: dict) -> list[list[float]]:
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "MultiLineString":
        pts: list[list[float]] = []
        for part in coords:
            pts.extend(part)
        return pts
    return list(coords)


def line_endpoints(geom: dict) -> tuple[Point, Point]:
    pts = _flatten_line(geom)
    return (pts[0][0], pts[0][1]), (pts[-1][0], pts[-1][1])


def line_centroid(geom: dict) -> Point:
    pts = _flatten_line(geom)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def signed_side(start: Point, end: Point, pt: Point) -> float:
    """> 0 : pt is left of travel start->end;  < 0 : right;  ~0 : on the line."""
    return (end[0] - start[0]) * (pt[1] - start[1]) - (end[1] - start[1]) * (pt[0] - start[0])


def dominant_axis(start: Point, end: Point) -> str:
    """'ns' if the segment runs more north-south, else 'ew'."""
    return "ns" if abs(end[1] - start[1]) >= abs(end[0] - start[0]) else "ew"
