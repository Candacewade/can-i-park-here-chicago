"""Load and query the canonical parking-location registry.

A ``location_id`` is the single source of truth for *where* the user is parking.
The frontend selectors resolve to one; the agent and data clients only ever use
the id and the structured fields hanging off it -- never a free-text address.

Today the registry is a small hand-written fixture file (real Chicago blocks,
see fixtures.json). The public API here is designed so Slice 5 can swap in a
file generated from official street + boundary geometry without touching callers.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

from app.config import LOCATIONS_FIXTURE_PATH

Side = Literal["north", "south", "east", "west"]
Parity = Literal["odd", "even", "any"]

# City "street_name" carries neither direction nor type -- those are separate
# columns. Strip a leading direction and a trailing type to match it.
_STREET_TYPES = {
    "AVE", "ST", "BLVD", "PKWY", "DR", "PL", "CT", "RD", "LN", "TER",
    "SQ", "ROW", "WAY", "HWY", "EXPY", "PLZ", "XING", "CRES",
}


class LocationNotFoundError(KeyError):
    """Raised when a location_id does not resolve against the registry."""


class ChicagoParkingLocation(BaseModel):
    """One canonical parking segment: a street, a block, and a side."""

    location_id: str
    neighborhood: str
    street_name: str = Field(description="Display name incl. direction, e.g. 'W Wrightwood Ave'.")
    from_cross_street: str
    to_cross_street: str
    side: Side
    address_parity: Parity = "any"
    address_range_low: int
    address_range_high: int

    # Fields City parking datasets need:
    street_sweeping_ward: str | None = None
    street_sweeping_section: str | None = None

    latitude: float | None = None
    longitude: float | None = None

    @property
    def representative_address(self) -> int:
        """A single house number inside the block, for point-in-range queries."""
        return (self.address_range_low + self.address_range_high) // 2

    @property
    def base_street_name(self) -> str:
        """Bare street name: no leading direction, no trailing type (matches City 'street_name')."""
        name = re.sub(r"^[NSEW]\s+", "", self.street_name).strip()
        parts = name.split()
        if len(parts) > 1 and parts[-1].upper().rstrip(".") in _STREET_TYPES:
            parts = parts[:-1]
        return " ".join(parts)

    @property
    def street_direction(self) -> str | None:
        m = re.match(r"^([NSEW])\s+", self.street_name)
        return m.group(1) if m else None

    def human_summary(self) -> str:
        return (
            f"{self.street_name} between {self.from_cross_street} and "
            f"{self.to_cross_street}, {self.side} side ({self.neighborhood})"
        )


@lru_cache(maxsize=1)
def _load() -> dict[str, ChicagoParkingLocation]:
    raw = json.loads(LOCATIONS_FIXTURE_PATH.read_text())
    out: dict[str, ChicagoParkingLocation] = {}
    for row in raw["locations"]:
        loc = ChicagoParkingLocation.model_validate(row)
        out[loc.location_id] = loc
    return out


def get_location(location_id: str) -> ChicagoParkingLocation:
    try:
        return _load()[location_id]
    except KeyError as exc:
        raise LocationNotFoundError(
            f"Unknown location_id {location_id!r}. Not in the supported Chicago registry."
        ) from exc


def list_locations() -> list[ChicagoParkingLocation]:
    return list(_load().values())


def registry_summary() -> dict:
    locs = list_locations()
    return {
        "count": len(locs),
        "neighborhoods": sorted({loc.neighborhood for loc in locs}),
        "generated": False,
        "source": "development fixtures (real Chicago blocks)",
    }
