"""Snow-route status for a block.

Source: City of Chicago "Snow Route Parking Restrictions" (Socrata
``i6k4-giaj``) -- 144 arterial stretches where on-street parking is banned once
2+ inches of snow accumulates (all rows ``restrict_t = "2 INCH"``).

The dataset gives ``on_street`` / ``from_stree`` / ``to_street`` but no address
ranges, and our blocks are finer-grained, so we match on street name + direction:
if the block's street is a named 2-inch route, the block is flagged.

A bare route match is advisory -- the ban only bites with snow. Whether it is
*active* is decided in the rule engine using the agent's weather evidence.
"""

from __future__ import annotations

from datetime import datetime

from app.config import CHICAGO_TZ, DATASET_SNOW_ROUTES
from app.locations.registry import ChicagoParkingLocation
from app.models.evidence import EvidenceStatus, SnowRouteEvidence, SourceProvenance
from app.services.socrata import SocrataClient, SocrataError

_SOURCE_NAME = "City of Chicago -- Snow Route Parking Restrictions"


def in_overnight_ban_period(when: datetime) -> bool:
    """The Dec 1 - Apr 1 winter overnight-ban season (calendar only)."""
    local = when.astimezone(CHICAGO_TZ)
    return local.month == 12 or local.month <= 3 or (local.month == 4 and local.day == 1)


def _norm(s: str | None) -> str:
    return (s or "").strip().upper().replace(".", "")


def get_snow_route_evidence(
    location: ChicagoParkingLocation,
    interval_start: datetime,
    interval_end: datetime,
    client: SocrataClient | None = None,
) -> SnowRouteEvidence:
    client = client or SocrataClient()

    direction = _norm(location.street_direction)
    street = _norm(location.base_street_name).replace("'", "''")
    # on_street looks like "W ARMITAGE AVE" -- match the bare name, tolerate the type.
    params = {
        "$where": f"upper(on_street) like '%{street}%'",
        "$select": "on_street,from_stree,to_street",
        "$limit": "200",
    }
    provenance = SourceProvenance(
        source_name=_SOURCE_NAME,
        source_dataset_id=DATASET_SNOW_ROUTES,
        retrieved_at=datetime.now(tz=CHICAGO_TZ),
        query=client.query_url(DATASET_SNOW_ROUTES, params),
    )
    in_season = in_overnight_ban_period(interval_start) or in_overnight_ban_period(interval_end)

    try:
        rows = client.get_rows(DATASET_SNOW_ROUTES, params)
    except SocrataError as exc:
        return SnowRouteEvidence(
            status=EvidenceStatus.UNAVAILABLE,
            provenance=provenance,
            in_overnight_ban_period=in_season,
            notes=[f"Could not verify snow routes: {exc}"],
        )

    match = None
    for row in rows:
        on = _norm(row.get("on_street"))
        toks = on.split()
        # require the street token present and, if the block has a direction, it matches
        dir_ok = not direction or direction in toks or toks[0] == direction
        if street.split()[0] in toks and dir_ok:
            match = row
            break

    if match is None:
        return SnowRouteEvidence(
            status=EvidenceStatus.VERIFIED,
            provenance=provenance,
            is_two_inch_route=False,
            in_overnight_ban_period=in_season,
            notes=["Block is not on a City 2-inch snow route."],
        )

    return SnowRouteEvidence(
        status=EvidenceStatus.VERIFIED,
        provenance=provenance,
        is_two_inch_route=True,
        on_street=match.get("on_street"),
        in_overnight_ban_period=in_season,
        ban_active=False,  # set True by the engine only with verified >=2in weather
        notes=[
            "Block is on a 2-inch snow route: parking is banned here whenever 2+ "
            "inches of snow has accumulated."
        ],
    )
