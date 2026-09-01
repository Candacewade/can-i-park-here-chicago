import pytest

from app.locations.registry import (
    LocationNotFoundError,
    get_location,
    list_locations,
)


def test_known_location_resolves():
    loc = get_location("wrightwood-3300w-north")
    assert loc.neighborhood == "Logan Square"
    assert loc.side == "north"


def test_unknown_location_raises():
    with pytest.raises(LocationNotFoundError):
        get_location("not-a-real-block")


def test_street_name_parsing_matches_city_fields():
    loc = get_location("wrightwood-3300w-north")
    assert loc.base_street_name == "Wrightwood"   # no direction, no type
    assert loc.street_direction == "W"


def test_representative_address_inside_range():
    loc = get_location("george-3200w-north")
    assert loc.address_range_low <= loc.representative_address <= loc.address_range_high


def test_registry_non_empty():
    assert len(list_locations()) >= 5
