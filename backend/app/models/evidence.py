"""Normalized parking evidence.

Every data client converts messy City fields into one of these typed objects.
The critical invariant: a data-source failure produces ``status = UNAVAILABLE``,
never an empty "no restriction" result. The rule engine treats those very
differently.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EvidenceStatus(StrEnum):
    """Whether a piece of evidence was actually verified against authoritative data."""

    VERIFIED = "VERIFIED"          # We successfully retrieved and understood the data.
    UNAVAILABLE = "UNAVAILABLE"    # Source failed, timed out, or returned garbage.
    UNSUPPORTED = "UNSUPPORTED"    # We do not (yet) have a data source for this location.


class SourceProvenance(BaseModel):
    """Where a piece of evidence came from -- kept for debugging, not shown to users."""

    source_name: str
    source_dataset_id: str
    retrieved_at: datetime
    query: str | None = None


class ResidentialZoneEvidence(BaseModel):
    """Residential permit-parking status for the requested block + side."""

    status: EvidenceStatus
    provenance: SourceProvenance | None = None

    # Populated when status == VERIFIED:
    zone_required: str | None = Field(
        default=None, description="Permit zone required to park here, or None if unrestricted."
    )
    is_buffer: bool = Field(
        default=False,
        description="Buffer segment: no posted signs, but zone products are sold to residents.",
    )
    matched_segment: dict | None = Field(
        default=None, description="The raw City street-segment row we matched, for tracing."
    )
    notes: list[str] = Field(default_factory=list)


class StreetCleaningWindow(BaseModel):
    """A single scheduled street-cleaning occurrence overlapping the request."""

    date: datetime = Field(description="Local Chicago date of cleaning (time set to posted start).")
    start: datetime
    end: datetime
    description: str


class StreetCleaningEvidence(BaseModel):
    """Street-cleaning schedule for the requested block."""

    status: EvidenceStatus
    provenance: SourceProvenance | None = None

    # Populated when status == VERIFIED:
    ward: str | None = None
    section: str | None = None
    windows: list[StreetCleaningWindow] = Field(
        default_factory=list,
        description="Cleaning windows that intersect the requested interval, sorted by start.",
    )
    notes: list[str] = Field(default_factory=list)


class TemporaryClosure(BaseModel):
    """A single street-closure / public-way-use permit overlapping the request."""

    permit_number: str
    closure_type: str = Field(description="City 'streetclosure' value: Full / Curblane / Partial.")
    start: datetime
    end: datetime
    meter_posting_or_bagging: bool = Field(
        description="City flagged parking-meter posting/bagging for this permit."
    )
    work_description: str
    blocks_parking: bool = Field(
        description="Our deterministic read of whether this permit removes on-street parking."
    )


class TemporaryClosureEvidence(BaseModel):
    """Temporary street-closure permits affecting the requested block + interval."""

    status: EvidenceStatus
    provenance: SourceProvenance | None = None

    # Populated when status == VERIFIED:
    closures: list[TemporaryClosure] = Field(
        default_factory=list,
        description="Permits with parking impact that intersect the interval, sorted by start.",
    )
    notes: list[str] = Field(default_factory=list)


class ParkingEvidence(BaseModel):
    """The full evidence bundle handed to the deterministic evaluator."""

    residential: ResidentialZoneEvidence | None = None
    street_cleaning: StreetCleaningEvidence | None = None
    temporary_closure: TemporaryClosureEvidence | None = None
