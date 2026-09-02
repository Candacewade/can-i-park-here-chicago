"""Turn a watch + its deterministic decision (+ optional agent prose) into a
polished multipart email.

The status, move-by time, and whether an urgent alert fires are already fixed by
the rule engine. This module only *presents* them: it builds a list of render
nodes (see ``email_render``) that become both an HTML body and a plain-text
fallback. Agent prose, when present, is slotted into the single "context /
alternatives" section -- never appended as a second copy of the explanation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import CHICAGO_TZ
from app.locations.registry import ChicagoParkingLocation, LocationNotFoundError, get_location
from app.models.decision import DecisionReason, ParkingDecision, ParkingStatus
from app.monitor.email_render import (
    H1,
    H2,
    Actions,
    EmailDoc,
    Finding,
    Lines,
    P,
    Panel,
    Rule,
    render_html,
    render_text,
)
from app.monitor.links import change_spot_url, extend_time_url, unsubscribe_url
from app.monitor.models import Watch
from app.monitor.schedule import MessageType
from app.rules.engine import _fmt as _short_marker  # deterministic short Chicago label
from app.rules.nearby import find_legal_parking_nearby

_ARCH_NOTE = (
    "Parking status and move-by times are determined by a rules-based system using "
    "City of Chicago data. AI is used only to investigate additional context and make "
    "the explanation easier to understand."
)

_CATEGORY_LABEL = {
    "residential": "Residential parking",
    "street_cleaning": "Street cleaning",
    "temporary_closure": "Temporary street closures",
    "snow_route": "Snow route",
    "meter": "Metered parking",
}
_VERDICT_EMOJI = {"blocks": "❌", "limits": "⚠️", "allows": "✅", "unknown": "⚠️"}
_LATER_WORD = {
    "street_cleaning": "street-cleaning",
    "temporary_closure": "street-closure",
    "snow_route": "snow-route",
    "residential": "residential-permit",
}
_BECAUSE = {
    "street_cleaning": " because street cleaning begins then",
    "temporary_closure": " because a temporary street closure begins then",
    "snow_route": " because a snow-route restriction takes effect then",
    "residential": " because a residential permit restriction takes effect then",
}


@dataclass
class Email:
    subject: str
    body_text: str
    body_html: str | None = None


# --- helpers -------------------------------------------------------------

def _location(watch: Watch) -> ChicagoParkingLocation | None:
    try:
        return get_location(watch.location_id)
    except LocationNotFoundError:
        return None


def _block_line(loc: ChicagoParkingLocation | None, watch: Watch) -> str:
    if loc is None:
        return watch.location_id
    return f"{loc.street_name} between {loc.from_cross_street} and {loc.to_cross_street}"


def _place_line(loc: ChicagoParkingLocation | None) -> str | None:
    if loc is None:
        return None
    return f"📍 {loc.side.capitalize()} side · {loc.neighborhood}"


def _short_street(loc: ChicagoParkingLocation | None, watch: Watch) -> str:
    return loc.street_name if loc is not None else watch.location_id


def _short_when(dt) -> str:
    """A compact label for subject lines, e.g. 'Sep 10 at 9:00 AM'. Formatting
    only -- the authoritative wording is decision.move_by_display."""
    local = dt.astimezone(CHICAGO_TZ)
    hour12 = local.strftime("%I").lstrip("0") or "12"
    return f"{local.strftime('%b')} {local.day} at {hour12}:{local.strftime('%M %p')}"


def _split_caveat(detail: str) -> tuple[str, str]:
    """Pull a trailing parenthetical dataset caveat out into secondary text."""
    d = detail.strip()
    if d.endswith(")") and "(" in d:
        head, _, tail = d.rpartition("(")
        caveat = tail[:-1].strip()
        if caveat:
            caveat = caveat[0].upper() + caveat[1:]
        return head.strip(), caveat
    return d, ""


def _reason_by_category(decision: ParkingDecision) -> dict[str, DecisionReason]:
    """One reason per category -- the most restrictive one wins."""
    rank = {"blocks": 3, "limits": 2, "unknown": 2, "allows": 1}
    chosen: dict[str, DecisionReason] = {}
    for r in decision.reasons:
        cur = chosen.get(r.category)
        if cur is None or rank.get(r.verdict, 0) > rank.get(cur.verdict, 0):
            chosen[r.category] = r
    return chosen


def _primary_limit(decision: ParkingDecision) -> DecisionReason | None:
    """The limiting reason that actually sets move_by (the earliest one)."""
    if decision.move_by is None:
        return None
    marker = _short_marker(decision.move_by)
    for r in decision.reasons:
        if r.verdict == "limits" and marker in r.detail:
            return r
    return next((r for r in decision.reasons if r.verdict == "limits"), None)


def _later_limit_categories(decision: ParkingDecision, primary: DecisionReason | None) -> list[str]:
    out: list[str] = []
    for r in decision.reasons:
        if r.verdict == "limits" and r is not primary and r.category not in out:
            out.append(r.category)
    return out


def _strip_markdown(text: str) -> str:
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.M)     # headings
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)                  # bold
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*", r"\1", text)  # italics
    text = re.sub(r"^\s{0,3}[-*]\s+", "• ", text, flags=re.M)     # bullets
    return text


def _prose_paragraphs(prose: str) -> list[str]:
    cleaned = _strip_markdown(prose.strip())
    parts = re.split(r"\n\s*\n", cleaned)
    return [re.sub(r"\s*\n\s*", " ", p).strip() for p in parts if p.strip()]


def _why_findings(
    decision: ParkingDecision, primary: DecisionReason | None = None
) -> list[Finding]:
    nodes: list[Finding] = []
    for cat, r in _reason_by_category(decision).items():
        text, caveat = _split_caveat(r.detail)
        if primary is not None and r is primary:
            text = text.rstrip(".") + ". This is the first restriction that affects your stay."
        nodes.append(
            Finding(
                _VERDICT_EMOJI.get(r.verdict, "•"),
                _CATEGORY_LABEL.get(cat, cat.replace("_", " ").capitalize()),
                text,
                caveat,
            )
        )
    return nodes


def _nearby_options(watch: Watch, limit: int = 3):
    return find_legal_parking_nearby(
        watch.location_id, watch.start_time, watch.end_time, watch.permit_zone
    )[:limit]


def _alternatives_nodes(
    watch: Watch, decision: ParkingDecision, agent_prose: str | None, heading: str
) -> list:
    """The single place agent prose lands. With no agent, a deterministic nearby
    search fills it. Only ever rendered when an investigation actually happened."""
    nodes: list = [Rule(), H2(heading)]
    if agent_prose:
        nodes += [P(p) for p in _prose_paragraphs(agent_prose)]
        return nodes

    options = _nearby_options(watch)
    if options:
        best = options[0]
        nodes.append(P(best.summary))
        detail = [
            f"🚶 About {best.walk_minutes} min away",
            f"📏 Approximately {best.distance_km} km",
        ]
        if best.status == "LEGAL":
            detail.append(
                "✅ Legal for your entire parking window: "
                f"{decision.start_time_display} → {decision.end_time_display}"
            )
        elif best.move_by_display:
            detail.append(f"⚠️ Legal here until {best.move_by_display}")
        nodes.append(Lines(detail))
        if len(options) > 1:
            extra = "; ".join(
                f"{o.summary.split(' between ')[0]} (~{o.walk_minutes} min)" for o in options[1:]
            )
            nodes.append(P(f"Other options nearby: {extra}.", muted=True))
    else:
        nodes.append(
            P(
                "I checked nearby blocks for an option that would let you stay parked "
                f"through {decision.end_time_display}. No nearby block currently supports "
                "the full period."
            )
        )
    return nodes


def _footer_nodes(watch: Watch) -> list:
    return [
        Rule(),
        P("Can I Park Here? · Chicago Parking Monitor", muted=True, small=True),
        P(_ARCH_NOTE, muted=True, small=True),
        P(f"Watch ID: {watch.watch_id}", muted=True, small=True),
        Actions(
            [
                ("Extend parking time", extend_time_url(watch)),
                ("Change parking spot", change_spot_url(watch)),
                ("Stop monitoring this parking spot", unsubscribe_url(watch)),
            ]
        ),
    ]


# --- subject -----------------------------------------------------------

def _subject(msg: MessageType, decision: ParkingDecision) -> str:
    st = decision.status
    if msg is MessageType.URGENT:
        return "🚨 Urgent parking alert: Move your car now"
    if msg is MessageType.REMINDER_3D and decision.move_by:
        return f"⏰ Reminder: move your car by {_short_when(decision.move_by)}"
    if msg is MessageType.REMINDER_NIGHT_BEFORE and decision.move_by:
        return f"⏰ Tomorrow: move your car by {_short_when(decision.move_by)}"
    if st is ParkingStatus.LEGAL_UNTIL and decision.move_by:
        return f"🚗 Parking update: Move by {_short_when(decision.move_by)}"
    if st is ParkingStatus.LEGAL:
        return "✅ Daily parking check: You're still clear"
    if st is ParkingStatus.NOT_LEGAL:
        return "❌ Daily parking check: Not legal to park here"
    return "⚠️ Daily parking check: Couldn't verify your parking"


def _preheader(decision: ParkingDecision) -> str:
    return {
        ParkingStatus.LEGAL: "Your car is parked legally for your window.",
        ParkingStatus.LEGAL_UNTIL: f"Move by {decision.move_by_display or 'your deadline'}.",
        ParkingStatus.NOT_LEGAL: "Action needed: your car is not legally parked.",
        ParkingStatus.UNKNOWN: "We couldn't verify your parking.",
    }[decision.status]


# --- documents -------------------------------------------------------

def _urgent_doc(
    watch: Watch, decision: ParkingDecision, loc: ChicagoParkingLocation | None, prose: str | None
) -> EmailDoc:
    nodes: list = [H1("🚨 Time-Sensitive Parking Alert"), P(_block_line(loc, watch))]
    pl = _place_line(loc)
    if pl:
        nodes.append(P(pl, muted=True))
    nodes.append(Rule())

    nodes.append(Panel([("Status", "NOT LEGAL")], tone="bad"))
    nodes.append(P("You cannot legally park here for this parking window."))
    nodes.append(P(f"🗓️ {decision.start_time_display} → {decision.end_time_display}"))
    nodes.append(
        P("A verified parking restriction applies to this block, so this alert requires action.")
    )

    nodes.append(Rule())
    nodes.append(H2("⚠️ Why this is urgent"))
    by_cat = _reason_by_category(decision)
    blockers = [r for r in by_cat.values() if r.verdict == "blocks"]
    rest = [r for r in by_cat.values() if r.verdict != "blocks"]
    for r in blockers + rest:
        text, caveat = _split_caveat(r.detail)
        nodes.append(
            Finding(
                _VERDICT_EMOJI.get(r.verdict, "•"),
                _CATEGORY_LABEL.get(r.category, r.category.replace("_", " ").capitalize()),
                text,
                caveat,
            )
        )

    nodes += _alternatives_nodes(watch, decision, prose, "🅿️ Legal alternative nearby")

    nodes.append(Rule())
    nodes.append(H2("🚗 What you should do now"))
    nodes.append(
        P(
            f"Move your car from {_short_street(loc, watch)} and relocate it to a legal "
            "parking location as soon as possible."
        )
    )

    nodes += _footer_nodes(watch)
    return EmailDoc("Time-Sensitive Parking Alert", _preheader(decision), nodes)


def _daily_doc(
    watch: Watch,
    decision: ParkingDecision,
    msg: MessageType,
    loc: ChicagoParkingLocation | None,
    prose: str | None,
) -> EmailDoc:
    st = decision.status
    nodes: list = [H1("🚗 Daily Parking Check"), P(_block_line(loc, watch))]
    pl = _place_line(loc)
    if pl:
        nodes.append(P(pl, muted=True))
    nodes.append(Rule())

    nodes.append(H2("🗓️ Parking window"))
    nodes.append(P(f"{decision.start_time_display} → {decision.end_time_display}"))

    if st is ParkingStatus.LEGAL_UNTIL and decision.move_by_display:
        primary = _primary_limit(decision)
        because = _BECAUSE.get(primary.category, "") if primary else ""
        nodes.append(
            Panel(
                [("Status", "LEGAL UNTIL"), ("Move your car by", decision.move_by_display)],
                tone="warn",
            )
        )
        nodes.append(
            P(
                "Your car is legal to park here right now, but you'll need to move it "
                f"before {decision.move_by_display}{because}."
            )
        )
        nodes.append(Rule())
        nodes.append(H2("🔎 Why"))
        nodes += _why_findings(decision, primary)

        nodes.append(Rule())
        nodes.append(H2("⏰ Most important thing to know"))
        nodes.append(P(f"Move by {decision.move_by_display}.", strong=True))
        later = _later_limit_categories(decision, primary)
        if later:
            words = " and ".join(_LATER_WORD.get(c, c.replace("_", " ")) for c in later)
            nodes.append(
                P(
                    f"Additional {words} restrictions occur later in your requested parking "
                    "period, but they do not change your earliest move-by time."
                )
            )

        nodes += _alternatives_nodes(watch, decision, prose, "🅿️ Nearby parking")

        nodes.append(Rule())
        nodes.append(H2("✅ Your next step"))
        nodes.append(P(f"Move your car before {decision.move_by_display}.", strong=True))

    elif st is ParkingStatus.LEGAL:
        nodes.append(Panel([("Status", "LEGAL")], tone="ok"))
        nodes.append(
            P(
                "Your car is parked legally for your requested window. "
                "Nothing needs to change right now."
            )
        )
        nodes.append(Rule())
        nodes.append(H2("🔎 Why"))
        nodes += _why_findings(decision)

    elif st is ParkingStatus.NOT_LEGAL:
        nodes.append(Panel([("Status", "NOT LEGAL")], tone="bad"))
        nodes.append(P("You cannot legally park here for this parking window."))
        nodes.append(Rule())
        nodes.append(H2("🔎 Why"))
        nodes += _why_findings(decision)
        nodes += _alternatives_nodes(watch, decision, prose, "🅿️ Legal alternative nearby")
        nodes.append(Rule())
        nodes.append(H2("🚗 What you should do now"))
        nodes.append(
            P(
                f"Move your car from {_short_street(loc, watch)} and relocate it to a legal "
                "parking spot as soon as possible."
            )
        )

    else:  # UNKNOWN
        nodes.append(Panel([("Status", "COULD NOT VERIFY")], tone="warn"))
        nodes.append(
            P("We could not safely confirm whether you can park here for your requested window.")
        )
        nodes.append(Rule())
        nodes.append(H2("🔎 What we could and couldn't check"))
        nodes += _why_findings(decision)
        for u in decision.unknown_reasons:
            nodes.append(Finding("⚠️", "Not verified", u))

    nodes += _footer_nodes(watch)
    return EmailDoc("Daily Parking Check", _preheader(decision), nodes)


def compose_email(
    watch: Watch,
    decision: ParkingDecision,
    msg: MessageType,
    agent_prose: str | None = None,
) -> Email:
    loc = _location(watch)
    prose = agent_prose.strip() if agent_prose and agent_prose.strip() else None
    if msg is MessageType.URGENT:
        doc = _urgent_doc(watch, decision, loc, prose)
    else:
        doc = _daily_doc(watch, decision, msg, loc, prose)
    return Email(
        subject=_subject(msg, decision),
        body_text=render_text(doc),
        body_html=render_html(doc),
    )
