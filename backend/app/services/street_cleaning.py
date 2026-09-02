"""Street-cleaning schedule for a block.

Source: City of Chicago "Street Sweeping Zones - 2026" (Socrata ``2r7q-emq3``).
Each row is one ward+section zone with a MultiPolygon geometry and month columns
``april`` .. ``november``, each a comma-separated list of scheduled days
(e.g. ``september = "3,4,8,9"``; a missing month means no sweeping that month).

The block's ward/section is set at address-resolution time (point-in-polygon).
If it is not cached, we fall back to a spatial query on the block's coordinates.

Known limitation: no time-of-day in the data. Chicago posts sweeping as roughly
9 AM - 3 PM; we use that as a documented default window.
"""

from __future__ import annotations

from datetime import datetime, time

from app.config import CHICAGO_TZ, DATASET_STREET_SWEEPING_ZONES
from app.locations.registry import ChicagoParkingLocation
from app.models.evidence import (
    EvidenceStatus,
    SourceProvenance,
    StreetCleaningEvidence,
    StreetCleaningWindow,
)
from app.services.socrata import SocrataClient, SocrataError

_SOURCE_NAME = "City of Chicago -- Street Sweeping Zones 2026"
_DEFAULT_START = time(9, 0)
_DEFAULT_END = time(15, 0)

_MONTH_COLUMNS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _iter_scheduled_dates(row: dict):
    """Yield (month, day) for every scheduled day in a sweeping-zone row."""
    for column, month in _MONTH_COLUMNS.items():
        for chunk in (row.get(column) or "").split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                yield month, int(chunk)


def _zone_query(location: ChicagoParkingLocation) -> dict:
    if location.street_sweeping_ward and location.street_sweeping_section:
        ward = location.street_sweeping_ward.zfill(2)
        section = location.street_sweeping_section.zfill(2)
        return {"$where": f"ward='{ward}' AND section='{section}'", "$limit": "5"}
    if location.latitude is not None and location.longitude is not None:
        return {
            "$where": f"intersects(the_geom,'POINT({location.longitude} {location.latitude})')",
            "$select": "ward,section,april,may,june,july,august,september,october,november",
            "$limit": "1",
        }
    return {}


def get_street_cleaning_evidence(
    location: ChicagoParkingLocation,
    start_time: datetime,
    end_time: datetime,
    client: SocrataClient | None = None,
) -> StreetCleaningEvidence:
    client = client or SocrataClient()
    params = _zone_query(location)
    if not params:
        return StreetCleaningEvidence(
            status=EvidenceStatus.UNSUPPORTED,
            notes=["No street-sweeping zone or coordinates are known for this block."],
        )

    provenance = SourceProvenance(
        source_name=_SOURCE_NAME,
        source_dataset_id=DATASET_STREET_SWEEPING_ZONES,
        retrieved_at=datetime.now(tz=CHICAGO_TZ),
        query=client.query_url(DATASET_STREET_SWEEPING_ZONES, params),
    )

    try:
        rows = client.get_rows(DATASET_STREET_SWEEPING_ZONES, params)
    except SocrataError as exc:
        return StreetCleaningEvidence(
            status=EvidenceStatus.UNAVAILABLE,
            provenance=provenance,
            ward=location.street_sweeping_ward,
            section=location.street_sweeping_section,
            notes=[f"Could not verify street cleaning: {exc}"],
        )

    if not rows:
        return StreetCleaningEvidence(
            status=EvidenceStatus.VERIFIED,
            provenance=provenance,
            notes=["No street-sweeping zone covers this block (or the season is over)."],
        )

    row = rows[0]
    ward = str(row.get("ward") or location.street_sweeping_ward or "").lstrip("0") or None
    section = str(row.get("section") or location.street_sweeping_section or "").lstrip("0") or None

    start_local = start_time.astimezone(CHICAGO_TZ)
    end_local = end_time.astimezone(CHICAGO_TZ)
    years = {start_local.year, end_local.year}

    windows: list[StreetCleaningWindow] = []
    for month, day in _iter_scheduled_dates(row):
        for year in years:
            try:
                d = datetime(year, month, day).date()
            except ValueError:
                continue
            w_start = datetime.combine(d, _DEFAULT_START, tzinfo=CHICAGO_TZ)
            w_end = datetime.combine(d, _DEFAULT_END, tzinfo=CHICAGO_TZ)
            if w_end <= start_local or w_start >= end_local:
                continue
            windows.append(
                StreetCleaningWindow(
                    date=w_start,
                    start=w_start,
                    end=w_end,
                    description=(
                        f"Scheduled street cleaning (ward {ward}, section {section}); "
                        f"posted hours assumed {_DEFAULT_START:%H:%M}-{_DEFAULT_END:%H:%M}."
                    ),
                )
            )

    windows.sort(key=lambda w: w.start)
    notes = [] if windows else ["No scheduled cleaning intersects the requested interval."]
    return StreetCleaningEvidence(
        status=EvidenceStatus.VERIFIED,
        provenance=provenance,
        ward=ward,
        section=section,
        windows=windows,
        notes=notes,
    )
