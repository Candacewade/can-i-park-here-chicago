"""Residential permit-parking status for a block + side.

Source: City of Chicago "Permit Parking Zones" (Socrata ``qiag-khha``) -- every
street segment the City Council has placed in a Residential Parking Zone, with
address range, side (odd/even), and zone number.
"""

from __future__ import annotations

from datetime import datetime

from app.config import CHICAGO_TZ, DATASET_RESIDENTIAL_ZONES
from app.locations.registry import ChicagoParkingLocation
from app.models.evidence import (
    EvidenceStatus,
    ResidentialZoneEvidence,
    SourceProvenance,
)
from app.services.socrata import SocrataClient, SocrataError

_SOURCE_NAME = "City of Chicago -- Permit Parking Zones"


def _parity_matches(odd_even: str | None, location: ChicagoParkingLocation) -> bool:
    """City ``odd_even``: 'O'/'E' restrict to that parity; blank applies to both."""
    oe = (odd_even or "").strip().upper()
    if oe not in {"O", "E"}:
        return True
    if location.address_parity == "any":
        return True
    return (oe == "O" and location.address_parity == "odd") or (
        oe == "E" and location.address_parity == "even"
    )


def _range_contains(row: dict, address: int) -> bool:
    try:
        lo = int(float(row["address_range_low"]))
        hi = int(float(row["address_range_high"]))
    except (KeyError, TypeError, ValueError):
        return False
    return min(lo, hi) <= address <= max(lo, hi)


def get_residential_zone_evidence(
    location: ChicagoParkingLocation,
    client: SocrataClient | None = None,
) -> ResidentialZoneEvidence:
    client = client or SocrataClient()
    street = location.base_street_name.upper().replace("'", "''")
    params = {
        "$where": f"upper(street_name)='{street}' AND status='ACTIVE'",
        "$limit": "400",
    }
    provenance = SourceProvenance(
        source_name=_SOURCE_NAME,
        source_dataset_id=DATASET_RESIDENTIAL_ZONES,
        retrieved_at=datetime.now(tz=CHICAGO_TZ),
        query=client.query_url(DATASET_RESIDENTIAL_ZONES, params),
    )

    try:
        rows = client.get_rows(DATASET_RESIDENTIAL_ZONES, params)
    except SocrataError as exc:
        return ResidentialZoneEvidence(
            status=EvidenceStatus.UNAVAILABLE,
            provenance=provenance,
            notes=[f"Could not verify residential zone: {exc}"],
        )

    direction = (location.street_direction or "").upper()
    matches = [
        row
        for row in rows
        if _range_contains(row, location.representative_address)
        and _parity_matches(row.get("odd_even"), location)
        and (not direction or (row.get("street_direction") or "").upper() == direction)
    ]

    if not matches:
        return ResidentialZoneEvidence(
            status=EvidenceStatus.VERIFIED,
            provenance=provenance,
            zone_required=None,
            notes=["No residential permit-zone segment covers this block and side."],
        )

    # Prefer a posted (non-buffer) segment if both exist for the block.
    matches.sort(key=lambda r: (r.get("buffer", "N").upper() == "Y"))
    best = matches[0]
    is_buffer = (best.get("buffer") or "N").strip().upper() == "Y"
    return ResidentialZoneEvidence(
        status=EvidenceStatus.VERIFIED,
        provenance=provenance,
        zone_required=str(best.get("zone")).strip() if best.get("zone") else None,
        is_buffer=is_buffer,
        matched_segment=best,
        notes=(
            ["Buffer segment: no posted signs, but residents may buy zone products."]
            if is_buffer
            else []
        ),
    )
