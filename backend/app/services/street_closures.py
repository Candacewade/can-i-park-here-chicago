"""Temporary street-closure / public-way permits for a block.

Source: City of Chicago transportation permits (Socrata ``rzy5-8tax``) -- public
way openings, work-zone occupations, block parties, etc. Each carries a street +
address range, a date range, a closure type (Full / Curblane / Partial), and a
flag for parking-meter posting/bagging.

We keep only permits that (a) match the block's street, direction, and address
range, (b) overlap the requested interval in time, (c) are still Open and not
cancelled, and (d) our deterministic read says remove on-street parking.
"""

from __future__ import annotations

from datetime import datetime

from app.config import CHICAGO_TZ, DATASET_STREET_CLOSURES
from app.locations.registry import ChicagoParkingLocation
from app.models.evidence import (
    EvidenceStatus,
    SourceProvenance,
    TemporaryClosure,
    TemporaryClosureEvidence,
)
from app.services.socrata import SocrataClient, SocrataError

_SOURCE_NAME = "City of Chicago -- Transportation Permits / Street Closures"

# Closure types that take away the curb lane where cars park.
_PARKING_IMPACT_TYPES = {"FULL", "CURBLANE"}


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CHICAGO_TZ)
    # The dataset has occasional garbage dates (year 2105, 2112, ...).
    if not (2000 <= dt.year <= 2100):
        return None
    return dt


def _addr_overlap(row: dict, low: int, high: int) -> bool:
    try:
        rlo = int(float(row["streetnumberfrom"]))
        rhi = int(float(row["streetnumberto"]))
    except (KeyError, TypeError, ValueError):
        return False
    return min(rlo, rhi) <= max(low, high) and max(rlo, rhi) >= min(low, high)


def _classify(row: dict) -> bool:
    """Deterministic: does this permit remove on-street parking?"""
    ctype = (row.get("streetclosure") or "").strip().upper()
    if ctype in _PARKING_IMPACT_TYPES:
        return True
    if (row.get("parkingmeterpostingorbagging") or "").strip().upper() == "Y":
        return True
    return False


def get_street_closure_evidence(
    location: ChicagoParkingLocation,
    start_time: datetime,
    end_time: datetime,
    client: SocrataClient | None = None,
) -> TemporaryClosureEvidence:
    client = client or SocrataClient()

    street = location.base_street_name.upper().replace("'", "''")
    direction = (location.street_direction or "").upper()
    start_iso = start_time.astimezone(CHICAGO_TZ).date().isoformat()
    end_iso = end_time.astimezone(CHICAGO_TZ).date().isoformat()

    where = (
        f"upper(streetname)='{street}' "
        f"AND applicationstartdate < '{end_iso}T23:59:59' "
        f"AND applicationenddate > '{start_iso}T00:00:00' "
        f"AND applicationstartdate > '2000-01-01T00:00:00'"
    )
    if direction:
        where += f" AND upper(direction)='{direction}'"
    params = {"$where": where, "$limit": "200"}

    provenance = SourceProvenance(
        source_name=_SOURCE_NAME,
        source_dataset_id=DATASET_STREET_CLOSURES,
        retrieved_at=datetime.now(tz=CHICAGO_TZ),
        query=client.query_url(DATASET_STREET_CLOSURES, params),
    )

    try:
        rows = client.get_rows(DATASET_STREET_CLOSURES, params)
    except SocrataError as exc:
        return TemporaryClosureEvidence(
            status=EvidenceStatus.UNAVAILABLE,
            provenance=provenance,
            notes=[f"Could not verify temporary street closures: {exc}"],
        )

    start_local = start_time.astimezone(CHICAGO_TZ)
    end_local = end_time.astimezone(CHICAGO_TZ)
    closures: list[TemporaryClosure] = []

    for row in rows:
        if (row.get("applicationstatus") or "").strip().lower() != "open":
            continue
        if "cancel" in (row.get("currentmilestone") or "").strip().lower():
            continue
        if not _addr_overlap(row, location.address_range_low, location.address_range_high):
            continue

        c_start = _parse_dt(row.get("applicationstartdate"))
        c_end = _parse_dt(row.get("applicationenddate"))
        if c_start is None or c_end is None:
            continue
        if c_end <= start_local or c_start >= end_local:
            continue
        if not _classify(row):
            continue

        closures.append(
            TemporaryClosure(
                permit_number=str(row.get("applicationnumber") or row.get("uniquekey") or "?"),
                closure_type=(row.get("streetclosure") or "unknown").strip(),
                start=c_start,
                end=c_end,
                meter_posting_or_bagging=(
                    (row.get("parkingmeterpostingorbagging") or "").strip().upper() == "Y"
                ),
                work_description=(row.get("worktypedescription") or "").strip(),
                blocks_parking=True,
            )
        )

    closures.sort(key=lambda c: c.start)
    notes: list[str] = []
    if not closures:
        notes.append("No open permit with parking impact overlaps this block and interval.")

    return TemporaryClosureEvidence(
        status=EvidenceStatus.VERIFIED,
        provenance=provenance,
        closures=closures,
        notes=notes,
    )
