"""The canonical parking-location registry.

A ``location_id`` is the single source of truth for *where* the user is parking.
The agent and data clients only ever use the id and the structured fields hanging
off it -- never a free-text address.

Since Slice 5 the registry is populated by address resolution (see
``app/locations/resolve.py``) rather than hand-written. ``get_location`` reads a
self-populating ``blocks.json`` cache; on a miss it reconstructs the location
from the id (re-resolving against live Chicago geometry) and remembers it.
``fixtures.json`` is kept for tests / offline demos.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Literal

from pydantic import BaseModel, Field

from app.config import (
    BLOCKS_FILE,
    GH_BLOCKS_PATH,
    GH_WATCHES_BRANCH,
    GH_WATCHES_REPO,
    GH_WATCHES_TOKEN,
    LOCATIONS_FIXTURE_PATH,
)
from app.json_store import FileJsonStore, GitHubJsonStore

Side = Literal["north", "south", "east", "west"]
Parity = Literal["odd", "even", "any"]

_DIRECTIONS = {"N", "S", "E", "W"}
_STREET_TYPES = {
    "AVE", "ST", "BLVD", "PKWY", "DR", "PL", "CT", "RD", "LN", "TER",
    "SQ", "ROW", "WAY", "HWY", "EXPY", "PLZ", "XING", "CRES",
}

_lock = threading.Lock()


class LocationNotFoundError(KeyError):
    """Raised when a location_id does not resolve against the registry."""


class ChicagoParkingLocation(BaseModel):
    """One canonical parking segment: a street, a block, and a side."""

    location_id: str
    neighborhood: str = Field(description="Community area -- display only, never rule input.")
    street_name: str = Field(description="Display name incl. direction, e.g. 'N Clark St'.")
    from_cross_street: str
    to_cross_street: str
    side: Side
    address_parity: Parity = "any"
    address_number: int | None = None
    zip_code: str | None = None
    address_range_low: int
    address_range_high: int

    street_sweeping_ward: str | None = None
    street_sweeping_section: str | None = None

    latitude: float | None = None
    longitude: float | None = None

    @property
    def representative_address(self) -> int:
        """A house number inside the block -- the exact one when known."""
        if self.address_number is not None:
            return self.address_number
        return (self.address_range_low + self.address_range_high) // 2

    @property
    def base_street_name(self) -> str:
        """Bare street name: no leading direction, no trailing type (matches City 'street_nam')."""
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


# --- location_id <-> street slug -------------------------------------

def slug_for_street(pre_dir: str, name: str, suffix: str) -> str:
    parts = [pre_dir, name, suffix]
    raw = "-".join(p for p in parts if p)
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")


def side_from_slug(location_id: str) -> tuple[str, str, str, int, str] | None:
    """'n-clark-st-2400-west' -> ('N', 'CLARK', 'ST', 2400, 'west'), or None."""
    m = re.match(r"^(.*)-(\d+)-(north|south|east|west)$", location_id)
    if not m:
        return None
    street_slug, block, side = m.group(1), int(m.group(2)), m.group(3)
    tokens = [t.upper() for t in street_slug.split("-") if t]
    if not tokens:
        return None
    pre = tokens.pop(0) if tokens[0] in _DIRECTIONS else ""
    suffix = tokens.pop() if len(tokens) > 1 and tokens[-1] in _STREET_TYPES else ""
    return pre, " ".join(tokens), suffix, block, side


# --- storage --------------------------------------------------------

def _blocks_store() -> FileJsonStore | GitHubJsonStore:
    if GH_WATCHES_REPO and GH_WATCHES_TOKEN:
        return GitHubJsonStore(
            GH_WATCHES_REPO, GH_WATCHES_TOKEN, GH_BLOCKS_PATH, GH_WATCHES_BRANCH
        )
    return FileJsonStore(BLOCKS_FILE)


_cache: dict[str, ChicagoParkingLocation] | None = None


def _all() -> dict[str, ChicagoParkingLocation]:
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        out: dict[str, ChicagoParkingLocation] = {}
        try:
            fixtures = json.loads(LOCATIONS_FIXTURE_PATH.read_text())["locations"]
            for row in fixtures:
                loc = ChicagoParkingLocation.model_validate(row)
                out[loc.location_id] = loc
        except (OSError, ValueError, KeyError):
            pass
        for lid, row in _blocks_store().load().items():
            try:
                out[lid] = ChicagoParkingLocation.model_validate(row)
            except ValueError:
                continue
        _cache = out
        return _cache


def remember_location(loc: ChicagoParkingLocation) -> None:
    """Persist a resolved location into blocks.json (and the in-process cache)."""
    with _lock:
        store = _blocks_store()
        data = store.load()
        data[loc.location_id] = json.loads(loc.model_dump_json())
        store.save(data)
        if _cache is not None:
            _cache[loc.location_id] = loc


def get_location(location_id: str) -> ChicagoParkingLocation:
    found = _all().get(location_id)
    if found is not None:
        return found

    # Cache miss: reconstruct from the id against live Chicago geometry.
    from app.locations.resolve import resolve_location_id

    loc = resolve_location_id(location_id)
    if loc is None:
        raise LocationNotFoundError(
            f"Unknown location_id {location_id!r}. Could not resolve it against "
            "Chicago street data."
        )
    remember_location(loc)
    return loc


def list_locations() -> list[ChicagoParkingLocation]:
    return list(_all().values())


def registry_summary() -> dict:
    locs = list_locations()
    return {
        "count": len(locs),
        "neighborhoods": sorted({loc.neighborhood for loc in locs}),
        "generated": True,
        "source": "resolved from Chicago street geometry (self-populating blocks.json)",
    }


def reset_cache() -> None:
    """Test helper."""
    global _cache
    with _lock:
        _cache = None
