"""Nearby special-event context for a block.

Events that actually remove parking (Festival/Parade/Athletic with a Full or
Curblane closure) are already handled by ``street_closures.py``. This is the
*context* layer for the agent: nearby permitted events during the interval that
mean crowds and congestion even if parking is technically legal.

Source: the same transportation-permits dataset (``rzy5-8tax``); event rows carry
point geometry (`latitude`/`longitude`).
"""

from __future__ import annotations

from datetime import datetime

from app.config import CHICAGO_TZ, DATASET_EVENTS, NEARBY_RADIUS_KM
from app.geo import approx_walk_minutes, haversine_km
from app.locations.registry import ChicagoParkingLocation
from app.models.evidence import (
    EventImpactEvidence,
    EvidenceStatus,
    NearbyEvent,
    SourceProvenance,
)
from app.services.socrata import SocrataClient, SocrataError

_SOURCE_NAME = "City of Chicago -- Transportation Permits (event work types)"
_EVENT_WORKTYPES = (
    "Festival", "Block Party", "Athletic", "Parade", "Filming",
    "Sidewalk Sale", "Farmer's Market", "Assembly",
)


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CHICAGO_TZ)
    return dt if 2000 <= dt.year <= 2100 else None


def get_nearby_events(
    location: ChicagoParkingLocation,
    interval_start: datetime,
    interval_end: datetime,
    client: SocrataClient | None = None,
) -> EventImpactEvidence:
    client = client or SocrataClient()

    start_iso = interval_start.astimezone(CHICAGO_TZ).date().isoformat()
    end_iso = interval_end.astimezone(CHICAGO_TZ).date().isoformat()
    worktypes = ",".join(f"'{w}'" for w in _EVENT_WORKTYPES)
    params = {
        "$where": (
            f"worktypedescription in ({worktypes}) "
            f"AND applicationstatus='Open' "
            f"AND applicationstartdate < '{end_iso}T23:59:59' "
            f"AND applicationenddate > '{start_iso}T00:00:00' "
            f"AND applicationstartdate > '2000-01-01T00:00:00' "
            f"AND latitude IS NOT NULL"
        ),
        "$limit": "400",
    }
    provenance = SourceProvenance(
        source_name=_SOURCE_NAME,
        source_dataset_id=DATASET_EVENTS,
        retrieved_at=datetime.now(tz=CHICAGO_TZ),
        query=client.query_url(DATASET_EVENTS, params),
    )

    if location.latitude is None or location.longitude is None:
        return EventImpactEvidence(
            status=EvidenceStatus.UNSUPPORTED,
            provenance=provenance,
            notes=["No coordinates for this block; cannot compute nearby events."],
        )

    try:
        rows = client.get_rows(DATASET_EVENTS, params)
    except SocrataError as exc:
        return EventImpactEvidence(
            status=EvidenceStatus.UNAVAILABLE,
            provenance=provenance,
            notes=[f"Could not verify nearby events: {exc}"],
        )

    events: list[NearbyEvent] = []
    for row in rows:
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        km = haversine_km(location.latitude, location.longitude, lat, lon)
        if km > NEARBY_RADIUS_KM:
            continue
        e_start = _parse_dt(row.get("applicationstartdate"))
        e_end = _parse_dt(row.get("applicationenddate"))
        if e_start is None or e_end is None:
            continue
        events.append(
            NearbyEvent(
                permit_number=str(row.get("applicationnumber") or "?"),
                name=(row.get("comments") or row.get("worktypedescription") or "event").strip(),
                start=e_start,
                end=e_end,
                distance_note=f"~{km:.1f} km ({approx_walk_minutes(km)} min walk)",
            )
        )

    events.sort(key=lambda e: e.start)
    return EventImpactEvidence(
        status=EvidenceStatus.VERIFIED,
        provenance=provenance,
        events=events,
        notes=[] if events else ["No permitted events near this block during the interval."],
    )
