"""Coordinates -> a plausible Chicago address. No live network, no 3rd-party
geocoding service -- only the official Street Center Lines dataset, the same
one the typed-address flow already queries."""

from __future__ import annotations

import pytest

from app.locations import resolve as resolve_mod
from app.locations.geocode import GeocodeResult
from app.locations.reverse import reverse_geocode
from tests.conftest import FakeSocrataClient

# A real N Clark St segment (same fixture shape as test_location_resolution.py).
_SEGMENT = {
    "pre_dir": "N", "street_nam": "CLARK", "street_typ": "ST",
    "l_f_add": "2400", "l_t_add": "2444", "r_f_add": "2401", "r_t_add": "2443",
    "fnode_id": "30329", "tnode_id": "8540",
    "the_geom": {"type": "MultiLineString", "coordinates": [[
        [-87.64048, 41.92558], [-87.64122, 41.92681],
    ]]},
}


class _RoutingSocrata:
    """Returns different canned rows per dataset -- the segment above answers
    both the spatial reverse-lookup query and resolve_address()'s own
    street-name lookup, which is realistic: it's genuinely the same segment."""

    def __init__(self, in_chicago=True, segment_rows=None):
        self._in_chicago = in_chicago
        self._segment_rows = _SEGMENT if segment_rows is None else segment_rows
        self.calls: list[str] = []

    def get_rows(self, dataset_id, params):
        self.calls.append(dataset_id)
        if dataset_id == "pr57-gg9e":
            if "fnode_id in" in params.get("$where", ""):
                return []  # no cross streets needed for these tests
            return [self._segment_rows] if self._segment_rows else []
        if dataset_id == "qqq8-j68g":
            return [{"name": "CHICAGO"}] if self._in_chicago else []
        return []

    def query_url(self, dataset_id, params):
        return f"https://example.test/{dataset_id}"


@pytest.fixture
def _mock_census(monkeypatch):
    def fake(number, street, zip_code):
        return GeocodeResult(
            matched_address=f"{number} N CLARK ST, CHICAGO, IL, {zip_code or '60614'}",
            latitude=41.9256, longitude=-87.6406,
            street_name="CLARK", pre_direction="N", suffix_type="ST",
            zip_code=zip_code or "60614", block_from=2400, block_to=2444,
            tiger_side="L", tiger_line_id="111767305",
        )
    monkeypatch.setattr(resolve_mod, "census_geocode", fake)


# A point right next to the N Clark St segment above.
_NEARBY_LAT, _NEARBY_LON = 41.92619, -87.64065


def test_reverse_geocode_finds_the_segment_and_resolves(_mock_census):
    result = reverse_geocode(lat=_NEARBY_LAT, lon=_NEARBY_LON, client=_RoutingSocrata())

    assert result is not None
    assert result.in_chicago is True
    assert result.locations
    loc = next(iter(result.locations.values()))
    assert loc.street_name == "N Clark St"
    assert loc.address_range_low <= loc.address_number <= loc.address_range_high


def test_reverse_geocode_returns_none_with_nothing_nearby(_mock_census):
    assert reverse_geocode(lat=_NEARBY_LAT, lon=_NEARBY_LON, client=FakeSocrataClient()) is None


def test_reverse_geocode_returns_none_when_segment_has_no_address_range(_mock_census):
    bad_segment = {**_SEGMENT, "l_f_add": "0", "l_t_add": "0", "r_f_add": "0", "r_t_add": "0"}
    client = _RoutingSocrata(segment_rows=bad_segment)
    assert reverse_geocode(lat=_NEARBY_LAT, lon=_NEARBY_LON, client=client) is None


def test_reverse_geocode_outside_chicago_boundary(_mock_census):
    result = reverse_geocode(
        lat=_NEARBY_LAT, lon=_NEARBY_LON, client=_RoutingSocrata(in_chicago=False)
    )
    assert result is not None
    assert result.in_chicago is False
    assert not result.locations


def test_reverse_geocode_never_raises_on_a_socrata_outage(_mock_census):
    client = FakeSocrataClient(error="down")
    assert reverse_geocode(lat=_NEARBY_LAT, lon=_NEARBY_LON, client=client) is None
