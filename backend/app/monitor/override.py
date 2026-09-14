"""A per-watch, user-reported override of the deterministic verdict.

Real use case: the user sees a posted sign (e.g. a temporary/orange street-
cleaning sign) that the City dataset doesn't reflect, and wants their own
emails/alerts to follow what they actually saw instead of -- or in addition
to -- the verified data.

By explicit user request this is a FULL override, either direction: while
active it REPLACES `evaluate_parking()`'s output for this one watch's
messaging. This intentionally departs from this app's core safety principle
that only verified City data + the deterministic engine decide legality --
see docs/monitoring.md for that trade-off, spelled out. It is scoped tightly:
one watch, self-reported, auto-expiring, never written back to city data or
any other watch, and always clearly labeled in the UI/email as the user's own
report rather than a verified status.
"""

from __future__ import annotations

from datetime import datetime

from app.models.decision import DecisionReason, ParkingDecision, ParkingStatus
from app.monitor.models import Watch, WatchOverride
from app.rules.engine import _display as display
from app.rules.engine import _urgent_alert as urgent_alert

_VERDICT_FOR_STATUS = {
    ParkingStatus.NOT_LEGAL: "blocks",
    ParkingStatus.LEGAL_UNTIL: "limits",
    ParkingStatus.LEGAL: "allows",
}


def override_active(watch: Watch, now: datetime) -> bool:
    return watch.override is not None and now < watch.override.expires_at


def decision_from_override(
    override: WatchOverride, request_start: datetime, request_end: datetime
) -> ParkingDecision:
    """Build a ParkingDecision entirely from what the user reported -- no
    evidence, no rule engine. Urgent-alert timing reuses the exact same
    deterministic threshold (`URGENT_WINDOW_HOURS`) the real engine uses, so
    an overridden NOT_LEGAL/LEGAL_UNTIL still alerts consistently."""
    urgent, urgent_reason = urgent_alert(override.status, override.move_by)
    return ParkingDecision(
        status=override.status,
        move_by=override.move_by,
        reasons=[
            DecisionReason(
                category="user_reported",
                verdict=_VERDICT_FOR_STATUS[override.status],
                detail=f'You reported: "{override.note}"',
            )
        ],
        start_time_display=display(request_start),
        end_time_display=display(request_end),
        move_by_display=display(override.move_by) if override.move_by is not None else None,
        urgent_alert=urgent,
        urgent_reason=urgent_reason,
    )
