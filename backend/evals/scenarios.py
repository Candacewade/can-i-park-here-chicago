"""Eval scenarios. Each fixes the City data and asserts agent behaviour."""

from __future__ import annotations

from dataclasses import dataclass, field

# Reassurance phrases the agent must never use.
DEFAULT_FORBIDDEN = ["probably fine", "probably okay", "you're fine", "you should be fine",
                     "likely fine", "you'll be okay", "should be okay"]

_WRIGHTWOOD = "wrightwood-3300w-north"   # fixtures.json: even, 3300-3320, W, ward 35 sec 09


@dataclass
class Scenario:
    id: str
    description: str
    location_id: str
    start: str
    end: str
    permit_zone: str | None
    socrata: dict                         # {dataset_id: [rows] | {"error": msg}}
    weather: dict | None = None
    expected_status: str = "LEGAL"
    move_by_contains: str | None = None
    required_tools: set[str] = field(default_factory=set)
    forbidden_tools: set[str] = field(default_factory=set)
    must_say: list[str] = field(default_factory=list)
    must_not_say: list[str] = field(default_factory=lambda: list(DEFAULT_FORBIDDEN))

    def fixtures(self) -> dict:
        return {"socrata": self.socrata, "weather": self.weather}


def _zone_row(**kw):
    row = {"street_name": "WRIGHTWOOD", "street_direction": "W",
           "address_range_low": "3300", "address_range_high": "3320",
           "odd_even": "E", "zone": "143", "buffer": "N", "status": "ACTIVE"}
    row.update(kw)
    return row


SCENARIOS: list[Scenario] = [
    Scenario(
        id="legal_clear",
        description="Summer overnight, no residential zone, nothing scheduled -> LEGAL, "
                    "the agent needs no investigation and must not reassure loosely.",
        location_id=_WRIGHTWOOD,
        start="2026-09-08T19:00:00-05:00", end="2026-09-09T08:00:00-05:00",
        permit_zone=None,
        socrata={"qiag-khha": [], "2r7q-emq3": [{"ward": "35", "section": "09"}],
                 "rzy5-8tax": [], "i6k4-giaj": []},
        expected_status="LEGAL",
    ),
    Scenario(
        id="legal_until_street_cleaning",
        description="Street cleaning starts 9 AM mid-interval -> LEGAL_UNTIL 9:00 AM.",
        location_id=_WRIGHTWOOD,
        start="2026-09-08T21:00:00-05:00", end="2026-09-09T11:00:00-05:00",
        permit_zone=None,
        socrata={"qiag-khha": [], "rzy5-8tax": [], "i6k4-giaj": [],
                 "2r7q-emq3": [{"ward": "35", "section": "09", "september": "8,9"}]},
        expected_status="LEGAL_UNTIL",
        move_by_contains="9:00 AM",
        must_say=["9:00 AM"],
    ),
    Scenario(
        id="not_legal_permit_offers_alternative",
        description="Residential zone 143, driver has no permit -> NOT_LEGAL; the agent "
                    "should look up a legal alternative nearby.",
        location_id=_WRIGHTWOOD,
        start="2026-09-20T19:00:00-05:00", end="2026-09-21T09:00:00-05:00",
        permit_zone=None,
        socrata={"qiag-khha": [_zone_row()], "2r7q-emq3": [{"ward": "35", "section": "09"}],
                 "rzy5-8tax": [], "i6k4-giaj": []},
        expected_status="NOT_LEGAL",
        required_tools={"find_legal_parking_nearby"},
        must_say=["143"],
    ),
    Scenario(
        id="unknown_when_core_source_fails",
        description="Street-sweeping source errors -> UNKNOWN. The agent must report it "
                    "as unverified, never imply it's fine.",
        location_id=_WRIGHTWOOD,
        start="2026-09-08T19:00:00-05:00", end="2026-09-09T09:00:00-05:00",
        permit_zone=None,
        socrata={"qiag-khha": [], "rzy5-8tax": [], "i6k4-giaj": [],
                 "2r7q-emq3": {"error": "City portal returned HTTP 503"}},
        expected_status="UNKNOWN",
        must_say=["could not", "verif"],
        must_not_say=[*DEFAULT_FORBIDDEN, "you can park", "go ahead and park"],
    ),
    Scenario(
        id="winter_snow_route_active",
        description="Winter, block is a 2-inch snow route, forecast shows 3+ inches -> the "
                    "agent should check the weather; verdict NOT_LEGAL.",
        location_id=_WRIGHTWOOD,
        start="2026-01-20T19:00:00-06:00", end="2026-01-21T09:00:00-06:00",
        permit_zone=None,
        socrata={"qiag-khha": [], "rzy5-8tax": [], "2r7q-emq3": [{"ward": "35", "section": "09"}],
                 "i6k4-giaj": [{"on_street": "W WRIGHTWOOD AVE", "from_stree": "N SPAULDING AVE",
                                "to_street": "N KIMBALL AVE", "restrict_t": "2 INCH"}]},
        weather={"status": "VERIFIED", "expected_snow_inches": 3.2,
                 "max_snow_probability": 90, "summary": "About 3.2 in of snow expected"},
        expected_status="NOT_LEGAL",
        required_tools={"get_weather_outlook"},
        must_say=["snow"],
    ),
]
