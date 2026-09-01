"""Street-cleaning schedule for a block.

Source: City of Chicago "Street Sweeping Schedule - 2026" (Socrata ``u5ai-3efk``).
Rows are keyed by ward + section, then give, per month, the day numbers cleaning
is scheduled (e.g. SEPTEMBER "8,9").

Known limitation: the dataset carries no time-of-day. Chicago posts sweeping as
roughly 9 AM - 3 PM; we use that as a documented default window. See
docs/data-sources.md.
"""

from __future__ import annotations

from datetime import datetime, time

from app.config import CHICAGO_TZ, DATASET_STREET_SWEEPING
from app.locations.registry import ChicagoParkingLocation
from app.models.evidence import (
    EvidenceStatus,
    SourceProvenance,
    StreetCleaningEvidence,
    StreetCleaningWindow,
)
from app.services.socrata import SocrataClient, SocrataError

_SOURCE_NAME = "City of Chicago -- Street Sweeping Schedule 2026"
_DEFAULT_START = time(9, 0)
_DEFAULT_END = time(15, 0)

_MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def _iter_scheduled_dates(rows: list[dict]):
    """Yield (month, day) pairs for every scheduled cleaning date in the raw rows."""
    for row in rows:
        month = _MONTHS.get((row.get("month_name") or "").strip().upper())
        if month is None:
            try:
                month = int(row["month_number"])
            except (KeyError, TypeError, ValueError):
                continue
        for chunk in (row.get("dates") or "").split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                yield month, int(chunk)


def get_street_cleaning_evidence(
    location: ChicagoParkingLocation,
    start_time: datetime,
    end_time: datetime,
    client: SocrataClient | None = None,
) -> StreetCleaningEvidence:
    client = client or SocrataClient()

    if not location.street_sweeping_ward or not location.street_sweeping_section:
        return StreetCleaningEvidence(
            status=EvidenceStatus.UNSUPPORTED,
            notes=["No street-sweeping ward/section is known for this block."],
        )

    ward = location.street_sweeping_ward.zfill(2)
    section = location.street_sweeping_section.zfill(2)
    params = {
        "$where": f"ward='{ward}' AND section='{section}'",
        "$limit": "200",
    }
    provenance = SourceProvenance(
        source_name=_SOURCE_NAME,
        source_dataset_id=DATASET_STREET_SWEEPING,
        retrieved_at=datetime.now(tz=CHICAGO_TZ),
        query=client.query_url(DATASET_STREET_SWEEPING, params),
    )

    try:
        rows = client.get_rows(DATASET_STREET_SWEEPING, params)
    except SocrataError as exc:
        return StreetCleaningEvidence(
            status=EvidenceStatus.UNAVAILABLE,
            provenance=provenance,
            ward=ward,
            section=section,
            notes=[f"Could not verify street cleaning: {exc}"],
        )

    start_local = start_time.astimezone(CHICAGO_TZ)
    end_local = end_time.astimezone(CHICAGO_TZ)
    years = {start_local.year, end_local.year}

    windows: list[StreetCleaningWindow] = []
    for month, day in _iter_scheduled_dates(rows):
        for year in years:
            try:
                w_start = datetime.combine(
                    datetime(year, month, day).date(), _DEFAULT_START, tzinfo=CHICAGO_TZ
                )
                w_end = datetime.combine(
                    datetime(year, month, day).date(), _DEFAULT_END, tzinfo=CHICAGO_TZ
                )
            except ValueError:
                continue
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
    notes = []
    if not rows:
        notes.append("No sweeping schedule rows for this ward/section (season may be over).")
    elif not windows:
        notes.append("No scheduled cleaning intersects the requested interval.")

    return StreetCleaningEvidence(
        status=EvidenceStatus.VERIFIED,
        provenance=provenance,
        ward=ward,
        section=section,
        windows=windows,
        notes=notes,
    )
