"""Address -> canonical location resolution (Slice 5). No live network."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.geo import dominant_axis, point_in_polygon, signed_side
from app.locations import resolve as resolve_mod
from app.locations.geocode import GeocodeError, GeocodeResult, census_geocode
from app.locations.registry import side_from_slug, slug_for_street
from app.locations.resolve import resolve_address
from tests.conftest import FakeSocrataClient

# --- geo helpers -----------------------------------------------------

def test_signed_side_and_axis():
    # segment running due north; point to the west is "left"
    assert signed_side((0, 0), (0, 1), (-0.1, 0.5)) > 0
    assert signed_side((0, 0), (0, 1), (0.1, 0.5)) < 0
    assert dominant_axis((0, 0), (0, 1)) == "ns"
    assert dominant_axis((0, 0), (1, 0)) == "ew"


def test_point_in_polygon_square_with_hole():
    poly = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
        ],
    }
    assert point_in_polygon(poly, 1, 1) is True
    assert point_in_polygon(poly, 5, 5) is False   # in the hole
    assert point_in_polygon(poly, 20, 20) is False


# --- slug round-trip ----------------------------------------------

def test_slug_round_trip():
    lid = f"{slug_for_street('N', 'CLARK', 'ST')}-2400-west"
    assert lid == "n-clark-st-2400-west"
    assert side_from_slug(lid) == ("N", "CLARK", "ST", 2400, "west")
    assert side_from_slug("not-a-location") is None


# --- Census geocoder ---------------------------------------------

_CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


@respx.mock
def test_census_geocode_parses_match():
    respx.get(_CENSUS_URL).mock(return_value=httpx.Response(200, json={
        "result": {"addressMatches": [{
            "matchedAddress": "2400 N CLARK ST, CHICAGO, IL, 60614",
            "coordinates": {"x": -87.6406, "y": 41.9256},
            "addressComponents": {
                "streetName": "CLARK", "preDirection": "N", "suffixType": "ST",
                "fromAddress": "2400", "toAddress": "2444", "zip": "60614",
            },
            "tigerLine": {"side": "L", "tigerLineId": "111767305"},
        }]}
    }))
    g = census_geocode(2400, "N Clark St", "60614")
    assert g.street_name == "CLARK" and g.pre_direction == "N"
    assert g.block_from == 2400 and g.block_to == 2444
    assert (g.latitude, g.longitude) == (41.9256, -87.6406)


@respx.mock
def test_census_geocode_no_match_raises():
    respx.get(_CENSUS_URL).mock(
        return_value=httpx.Response(200, json={"result": {"addressMatches": []}})
    )
    with pytest.raises(GeocodeError):
        census_geocode(99999, "Nowhere Rd", "60000")


# --- full resolution (mocked geocoder + fake socrata) -----------

_SEGMENT = {
    "trans_id": "103516", "pre_dir": "N", "street_nam": "CLARK", "street_typ": "ST",
    "l_f_add": "2400", "l_t_add": "2444", "r_f_add": "2401", "r_t_add": "2443",
    "fnode_id": "30329", "tnode_id": "8540",
    "the_geom": {"type": "MultiLineString", "coordinates": [[
        [-87.64048, 41.92558], [-87.64122, 41.92681],
    ]]},
}
_CROSS = [
    {"street_nam": "FULLERTON", "street_typ": "PKWY", "pre_dir": "W",
     "fnode_id": "30329", "tnode_id": "1"},
    {"street_nam": "ARLINGTON", "street_typ": "PL", "pre_dir": "W",
     "fnode_id": "2", "tnode_id": "8540"},
]


class _RoutingSocrata:
    """Returns different canned rows per dataset."""

    def __init__(self, in_chicago=True):
        self._in_chicago = in_chicago
        self.calls = []

    def get_rows(self, dataset_id, params):
        self.calls.append(dataset_id)
        if dataset_id == "pr57-gg9e":
            if "fnode_id in" in params.get("$where", ""):
                return _CROSS
            return [_SEGMENT]
        if dataset_id == "qqq8-j68g":
            return [{"name": "CHICAGO"}] if self._in_chicago else []
        if dataset_id == "2r7q-emq3":
            return [{"ward": "43", "section": "03"}]
        if dataset_id == "igwz-8jzy":
            return [{"community": "LINCOLN PARK"}]
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


def test_resolve_address_full(_mock_census):
    r = resolve_address(2400, "N Clark St", "60614", client=_RoutingSocrata())
    assert r.in_chicago is True
    assert r.neighborhood == "Lincoln Park"
    assert set(r.side_options) == {"east", "west"}
    assert r.suggested_side == "west"          # even number on a N-S street
    assert r.side_confidence == "high"
    west = r.locations["west"]
    assert west.location_id == "n-clark-st-2400-west"
    assert west.street_sweeping_ward == "43" and west.street_sweeping_section == "03"
    assert west.from_cross_street == "W Fullerton Pkwy"
    assert west.address_number == 2400 and west.address_parity == "even"


def test_resolve_outside_chicago(_mock_census):
    r = resolve_address(2400, "N Clark St", "60614", client=_RoutingSocrata(in_chicago=False))
    assert r.in_chicago is False
    assert not r.locations
    assert any("outside" in n.lower() for n in r.notes)


def test_resolve_no_centerline_match(monkeypatch):
    monkeypatch.setattr(resolve_mod, "census_geocode",
                        lambda *a: (_ for _ in ()).throw(GeocodeError("down")))

    class NoSeg(FakeSocrataClient):
        def get_rows(self, dataset_id, params):
            return []

    r = resolve_address(500, "W Nowhere St", "", client=NoSeg())
    assert not r.locations
    assert any("centerline" in n.lower() for n in r.notes)
