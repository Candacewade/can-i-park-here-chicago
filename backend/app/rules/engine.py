"""``evaluate_parking(request, evidence) -> ParkingDecision``.

The only component that decides parking legality. Pure function, no I/O, no LLM.

Verdict precedence:  NOT_LEGAL  >  UNKNOWN  >  LEGAL_UNTIL  >  LEGAL

- A verified restriction active at the start time  -> NOT_LEGAL (you cannot park).
- Otherwise, any safety-required evidence not verified -> UNKNOWN.
- Otherwise, a verified restriction that begins during the interval -> LEGAL_UNTIL.
- Otherwise -> LEGAL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config import CHICAGO_TZ, DATASET_STREET_SWEEPING_ZONES, URGENT_WINDOW_HOURS
from app.models.decision import DecisionReason, ParkingDecision, ParkingStatus
from app.models.evidence import EvidenceStatus, ParkingEvidence
from app.models.requests import ParkingRequest
from app.rules.completeness import check_completeness

_RESIDENTIAL_DS = "qiag-khha"
_CLEANING_DS = DATASET_STREET_SWEEPING_ZONES  # the dataset street_cleaning.py actually queries
_CLOSURE_DS = "rzy5-8tax"
_SNOW_DS = "i6k4-giaj"


def _fmt(dt: datetime) -> str:
    """Short deterministic Chicago-local label, e.g. 'Wed Sep 9 9 AM'."""
    local = dt.astimezone(CHICAGO_TZ)
    hour12 = local.strftime("%I").lstrip("0") or "12"
    body = f"{local.strftime('%a %b')} {local.day} {hour12}:{local.strftime('%M %p')}"
    return body.replace(":00", "")


def _display(dt: datetime) -> str:
    """Full deterministic Chicago-local string, e.g. 'Tuesday, September 9, 2026 at 9:00 AM'."""
    local = dt.astimezone(CHICAGO_TZ)
    hour12 = local.strftime("%I").lstrip("0") or "12"
    return (
        f"{local.strftime('%A, %B')} {local.day}, {local.year} "
        f"at {hour12}:{local.strftime('%M %p')}"
    )


@dataclass
class _Conflict:
    category: str
    detail: str
    source: str
    move_by: datetime | None = None  # set => begins mid-interval (limit), not active now


def _residential_reasons(request: ParkingRequest, evidence: ParkingEvidence) -> tuple[
    list[DecisionReason], list[_Conflict]
]:
    r = evidence.residential
    if not r or r.status != EvidenceStatus.VERIFIED:
        return [], []
    if r.zone_required is None:
        return [DecisionReason(
            category="residential", verdict="allows",
            detail="Block is not in a residential permit zone.",
            source_dataset_id=_RESIDENTIAL_DS,
        )], []
    if r.is_buffer:
        return [DecisionReason(
            category="residential", verdict="allows",
            detail=(
                f"Buffer zone {r.zone_required}: no signs posted; "
                "on-street parking not restricted."
            ),
            source_dataset_id=_RESIDENTIAL_DS,
        )], []
    if request.permit_zone and request.permit_zone == r.zone_required:
        return [DecisionReason(
            category="residential", verdict="allows",
            detail=f"Zone {r.zone_required} permit required; your permit matches.",
            source_dataset_id=_RESIDENTIAL_DS,
        )], []
    held = f"zone {request.permit_zone}" if request.permit_zone else "no permit"
    detail = (
        f"Residential zone {r.zone_required} permit required to park here; you have {held}. "
        "(Posted hours are not in the City dataset; the zone is treated as in effect "
        "for your interval.)"
    )
    conflict = _Conflict("residential", detail, _RESIDENTIAL_DS)
    return [DecisionReason(
        category="residential", verdict="blocks", detail=detail, source_dataset_id=_RESIDENTIAL_DS,
    )], [conflict]


def _window_conflicts(
    request: ParkingRequest, windows, category: str, source: str, label
) -> tuple[list[DecisionReason], list[_Conflict]]:
    reasons: list[DecisionReason] = []
    conflicts: list[_Conflict] = []
    for w in windows:
        start = w.start if hasattr(w, "start") else w[0]
        end = w.end if hasattr(w, "end") else w[1]
        text = label(w)
        if start <= request.start_time < end:
            msg = f"{text} is in effect at your start time."
            reasons.append(DecisionReason(
                category=category, verdict="blocks", detail=msg, source_dataset_id=source,
            ))
            conflicts.append(_Conflict(category, msg, source))
        elif request.start_time < start < request.end_time:
            reasons.append(DecisionReason(
                category=category, verdict="limits",
                detail=f"{text} begins {_fmt(start)}, before your requested departure.",
                source_dataset_id=source,
            ))
            conflicts.append(_Conflict(
                category, f"{text} begins {_fmt(start)}.", source, move_by=start,
            ))
    return reasons, conflicts


def _street_cleaning_reasons(request, evidence):
    sc = evidence.street_cleaning
    if not sc or sc.status != EvidenceStatus.VERIFIED:
        return [], []
    if not sc.windows:
        return [DecisionReason(
            category="street_cleaning", verdict="allows",
            detail="No street cleaning scheduled during your interval.",
            source_dataset_id=_CLEANING_DS,
        )], []
    return _window_conflicts(
        request, sc.windows, "street_cleaning", _CLEANING_DS,
        lambda w: "Street cleaning",
    )


def _closure_reasons(request, evidence):
    tc = evidence.temporary_closure
    if not tc or tc.status != EvidenceStatus.VERIFIED:
        return [], []
    if not tc.closures:
        return [DecisionReason(
            category="temporary_closure", verdict="allows",
            detail="No temporary street-closure permit affects this block during your interval.",
            source_dataset_id=_CLOSURE_DS,
        )], []
    def label(c):
        work = c.work_description or "work zone"
        return f"Permit {c.permit_number} ({c.closure_type} closure: {work})"

    return _window_conflicts(request, tc.closures, "temporary_closure", _CLOSURE_DS, label)


def _snow_reasons(request, evidence):
    sr = evidence.snow_route
    if not sr or sr.status != EvidenceStatus.VERIFIED:
        return [], []
    if not sr.is_two_inch_route:
        return [DecisionReason(
            category="snow_route", verdict="allows",
            detail="Block is not on a City 2-inch snow route.",
            source_dataset_id=_SNOW_DS,
        )], []

    weather = evidence.weather
    snow_in = (
        weather.expected_snow_inches
        if weather and weather.status == EvidenceStatus.VERIFIED
        else None
    )
    if snow_in is not None and snow_in >= 2.0:
        msg = (
            f"This block is a 2-inch snow route and about {snow_in} in of snow is "
            "forecast during your interval -- on-street parking is banned and cars "
            "may be towed."
        )
        return [DecisionReason(
            category="snow_route", verdict="blocks", detail=msg, source_dataset_id=_SNOW_DS,
        )], [_Conflict("snow_route", msg, _SNOW_DS)]

    note = (
        "Advisory: this block is a 2-inch snow route. Parking is banned here only "
        "once 2+ inches of snow has accumulated."
    )
    if snow_in is not None:
        note += f" Current forecast: ~{snow_in} in."
    elif weather is None or weather.status != EvidenceStatus.VERIFIED:
        note += " Snowfall has not been verified."
    return [DecisionReason(
        category="snow_route", verdict="allows", detail=note, source_dataset_id=_SNOW_DS,
    )], []


def _urgent_alert(status: ParkingStatus, move_by: datetime | None) -> tuple[bool, str | None]:
    """Deterministic hard trigger for the Slice 4 monitor. The agent may prioritize
    and word the alert; it may not decide whether it fires."""
    if status is ParkingStatus.NOT_LEGAL:
        return True, "A verified restriction prevents parking here for this request."
    if status is ParkingStatus.LEGAL_UNTIL and move_by is not None:
        hours = (move_by - datetime.now(tz=CHICAGO_TZ)).total_seconds() / 3600
        if 0 <= hours <= URGENT_WINDOW_HOURS:
            return True, (
                f"The car must be moved by {_display(move_by)} -- within "
                f"{int(URGENT_WINDOW_HOURS)} hours."
            )
    return False, None


def evaluate_parking(request: ParkingRequest, evidence: ParkingEvidence) -> ParkingDecision:
    reasons: list[DecisionReason] = []
    conflicts: list[_Conflict] = []

    for fn in (_residential_reasons, _street_cleaning_reasons, _closure_reasons, _snow_reasons):
        r, c = fn(request, evidence)
        reasons.extend(r)
        conflicts.extend(c)

    blocking = [c for c in conflicts if c.move_by is None]
    limiting = [c for c in conflicts if c.move_by is not None]
    completeness = check_completeness(request, evidence)

    status = ParkingStatus.LEGAL
    move_by: datetime | None = None
    unknown_reasons: list[str] = []

    if blocking:
        # NOT_LEGAL: a verified restriction is active at the start time. Holds even
        # if other evidence is incomplete -- you still cannot park.
        status = ParkingStatus.NOT_LEGAL
    elif not completeness.complete:
        # UNKNOWN: a safety-required category could not be verified.
        status = ParkingStatus.UNKNOWN
        unknown_reasons = completeness.missing
    elif limiting:
        # LEGAL_UNTIL: fine now, but a verified restriction starts before departure.
        status = ParkingStatus.LEGAL_UNTIL
        move_by = min(c.move_by for c in limiting)  # type: ignore[type-var]

    urgent, urgent_reason = _urgent_alert(status, move_by)
    return ParkingDecision(
        status=status,
        move_by=move_by,
        reasons=reasons,
        unknown_reasons=unknown_reasons,
        start_time_display=_display(request.start_time),
        end_time_display=_display(request.end_time),
        move_by_display=_display(move_by) if move_by is not None else None,
        urgent_alert=urgent,
        urgent_reason=urgent_reason,
    )
