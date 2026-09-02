"""Turn a watch + its deterministic decision (+ optional agent output) into an
email. The status, move-by, and whether an urgent alert is warranted are already
fixed by the rule engine; this module only chooses wording."""

from __future__ import annotations

from dataclasses import dataclass

from app.locations.registry import LocationNotFoundError, get_location
from app.models.decision import ParkingDecision, ParkingStatus
from app.monitor.models import Watch
from app.monitor.schedule import MessageType
from app.rules.nearby import find_legal_parking_nearby

_STATUS_LINE = {
    ParkingStatus.LEGAL: "Your car is parked legally.",
    ParkingStatus.LEGAL_UNTIL: "Your car is legal for now, but you must move it.",
    ParkingStatus.NOT_LEGAL: "Your car is parked where it is NOT allowed.",
    ParkingStatus.UNKNOWN: "We could not verify your parking.",
}


@dataclass
class Email:
    subject: str
    body_text: str


def _block(watch: Watch) -> str:
    try:
        return get_location(watch.location_id).human_summary()
    except LocationNotFoundError:
        return watch.location_id


def _subject(msg: MessageType, decision: ParkingDecision, block: str) -> str:
    short_block = block.split(" between ")[0]
    if msg is MessageType.URGENT:
        return f"URGENT: {decision.urgent_reason or 'move your car'}"
    if msg is MessageType.REMINDER_3D:
        return f"Heads up: move your car by {decision.move_by_display}"
    if msg is MessageType.REMINDER_NIGHT_BEFORE:
        return f"Tomorrow: move your car by {decision.move_by_display}"
    # morning summary
    return {
        ParkingStatus.LEGAL: f"Parking OK - {short_block}",
        ParkingStatus.LEGAL_UNTIL: f"Move by {decision.move_by_display} - {short_block}",
        ParkingStatus.NOT_LEGAL: f"Parked illegally - {short_block}",
        ParkingStatus.UNKNOWN: f"Could not verify parking - {short_block}",
    }[decision.status]


def _nearby_block(watch: Watch, limit: int = 3) -> str:
    options = find_legal_parking_nearby(
        watch.location_id, watch.start_time, watch.end_time, watch.permit_zone
    )[:limit]
    if not options:
        return ""
    lines = ["", "Legal alternatives nearby:"]
    for o in options:
        tail = f" (legal until {o.move_by_display})" if o.move_by_display else ""
        lines.append(f"  - {o.summary} - {o.walk_minutes} min walk{tail}")
    return "\n".join(lines)


def compose_email(
    watch: Watch,
    decision: ParkingDecision,
    msg: MessageType,
    agent_prose: str | None = None,
) -> Email:
    block = _block(watch)
    lines: list[str] = []

    if msg is MessageType.URGENT:
        lines.append("TIME-SENSITIVE PARKING ALERT")
    elif msg in (MessageType.REMINDER_3D, MessageType.REMINDER_NIGHT_BEFORE):
        lines.append("Parking reminder")
    else:
        lines.append("Daily parking check")
    lines.append("")
    lines.append(block)
    lines.append(f"Window: {decision.start_time_display} -> {decision.end_time_display}")
    lines.append("")
    lines.append(f"STATUS: {decision.status.value} - {_STATUS_LINE[decision.status]}")
    if decision.move_by_display:
        lines.append(f"MOVE BY: {decision.move_by_display}")
    if decision.urgent_alert and decision.urgent_reason:
        lines.append(f"WHY IT'S URGENT: {decision.urgent_reason}")
    lines.append("")

    for r in decision.reasons:
        mark = {"blocks": "[x]", "limits": "[!]", "allows": "[ok]"}.get(r.verdict, "-")
        lines.append(f"  {mark} {r.category.replace('_', ' ')}: {r.detail}")
    for u in decision.unknown_reasons:
        lines.append(f"  [?] {u}")

    if agent_prose:
        # The agent already investigated and, where useful, listed alternatives.
        lines.append("")
        lines.append(agent_prose.strip())
    elif decision.status in (ParkingStatus.NOT_LEGAL, ParkingStatus.LEGAL_UNTIL) or (
        msg in (MessageType.URGENT, MessageType.REMINDER_NIGHT_BEFORE)
    ):
        # Deterministic fallback (no agent runtime): attach the nearby search.
        nb = _nearby_block(watch)
        if nb:
            lines.append(nb)

    lines.append("")
    lines.append("-" * 48)
    lines.append(
        f"You're monitoring parking at this block (watch {watch.watch_id}). "
        "The verdict above is produced by a deterministic rule engine over City "
        "of Chicago data; an AI assistant wrote the explanation."
    )
    return Email(subject=_subject(msg, decision, block), body_text="\n".join(lines))
