"""Fast checks on the eval suite -- no LLM, no network. The real run is
`python -m evals` (spends subscription usage, not in CI)."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models.requests import ParkingRequest
from evals.scenarios import SCENARIOS

_STATUSES = {"LEGAL", "NOT_LEGAL", "LEGAL_UNTIL", "UNKNOWN"}
_KNOWN_TOOLS = {
    "get_location_context", "get_weather_outlook", "get_snow_route_status",
    "get_nearby_events", "get_closure_detail", "find_legal_parking_nearby",
    "evaluate_parking_request", "list_supported_locations",
}


def test_scenarios_present_and_unique():
    assert len(SCENARIOS) >= 5
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("sc", SCENARIOS, ids=lambda s: s.id)
def test_scenario_is_well_formed(sc):
    # request parses
    req = ParkingRequest(
        location_id=sc.location_id, start_time=sc.start, end_time=sc.end,
        permit_zone=sc.permit_zone,
    )
    assert req.end_time > req.start_time
    assert isinstance(req.start_time, datetime)

    assert sc.expected_status in _STATUSES
    assert (sc.required_tools | sc.forbidden_tools) <= _KNOWN_TOOLS
    fx = sc.fixtures()
    assert isinstance(fx["socrata"], dict)
    for v in fx["socrata"].values():
        assert isinstance(v, list) or (isinstance(v, dict) and "error" in v)


def test_install_fixture_data_patches_socrata_and_weather(monkeypatch):
    from app.locations.registry import get_location
    from app.models.evidence import EvidenceStatus
    from app.services import weather as weather_mod
    from app.services.residential_zones import get_residential_zone_evidence
    from app.services.socrata import SocrataClient, SocrataError
    from app.testing.fixtures import install_fixture_data

    install_fixture_data({
        "socrata": {
            "qiag-khha": [{
                "street_name": "WRIGHTWOOD", "street_direction": "W",
                "address_range_low": "3300", "address_range_high": "3320",
                "odd_even": "E", "zone": "143", "buffer": "N", "status": "ACTIVE",
            }],
            "2r7q-emq3": {"error": "boom"},
        },
        "weather": {"status": "VERIFIED", "expected_snow_inches": 4.0},
    })

    loc = get_location("wrightwood-3300w-north")
    ev = get_residential_zone_evidence(loc, client=SocrataClient())
    assert ev.zone_required == "143"

    with pytest.raises(SocrataError):
        SocrataClient().get_rows("2r7q-emq3", {})

    w = weather_mod.get_weather_outlook(1.0, 2.0, loc, loc)
    assert w.status is EvidenceStatus.VERIFIED and w.expected_snow_inches == 4.0
