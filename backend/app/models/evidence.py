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


class SnowRouteEvidence(BaseModel):
    """Whether the block is on a City '2-inch' snow route. The ban only bites once
    >=2 inches accumulate, so ``ban_active`` is only True when weather evidence
    confirms it (set by the engine, not this client)."""

    status: EvidenceStatus
    provenance: SourceProvenance | None = None

    is_two_inch_route: bool = False
    on_street: str | None = None
    ban_active: bool = Field(
        default=False,
        description="True only if a 2-inch route AND >=2in is verified in the interval.",
    )
    in_overnight_ban_period: bool = Field(
        default=False,
        description="Interval overlaps the Dec 1 - Apr 1 2-7 AM overnight-ban season.",
    )
    notes: list[str] = Field(default_factory=list)


class WeatherOutlookEvidence(BaseModel):
    """NWS forecast for the block over the requested interval. A forecast, not a
    fact -- feeds the agent's risk narrative and (only when it confirms >=2 in on
    a 2-inch route) the snow_route verdict."""

    status: EvidenceStatus
    provenance: SourceProvenance | None = None

    expected_snow_inches: float | None = None
    max_snow_probability: int | None = None
    summary: str | None = None
    notes: list[str] = Field(default_factory=list)


class NearbyEvent(BaseModel):
    permit_number: str
    name: str
    start: datetime
    end: datetime
    distance_note: str = ""


class EventImpactEvidence(BaseModel):
    """Special-event permits near the block during the interval. Context only
    (congestion, crowds); parking-affecting events are already covered by
    temporary_closure."""

    status: EvidenceStatus
    provenance: SourceProvenance | None = None

    events: list[NearbyEvent] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ParkingEvidence(BaseModel):
    """The full evidence bundle handed to the deterministic evaluator.

    residential / street_cleaning / temporary_closure are the deterministic core
    (always gathered). snow_route is core in winter, otherwise optional. weather
    and events are only ever added by the agent's investigation wing.
    """

    residential: ResidentialZoneEvidence | None = None
    street_cleaning: StreetCleaningEvidence | None = None
    temporary_closure: TemporaryClosureEvidence | None = None
    snow_route: SnowRouteEvidence | None = None
    weather: WeatherOutlookEvidence | None = None
    events: EventImpactEvidence | None = None
