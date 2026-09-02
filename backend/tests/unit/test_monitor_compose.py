"""The polished daily / urgent email templates."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.config import CHICAGO_TZ
from app.models.decision import DecisionReason, ParkingDecision, ParkingStatus
from app.monitor import compose as compose_mod
from app.monitor.compose import compose_email
from app.monitor.models import Watch
from app.monitor.schedule import MessageType

NOW = datetime(2026, 9, 8, 8, 0, tzinfo=CHICAGO_TZ)


class _Loc:
    street_name = "W Grant Pl"
    from_cross_street = "N Cleveland Ave"
    to_cross_street = "N Geneva Ter"
    side = "north"
    neighborhood = "Lincoln Park"


@pytest.fixture(autouse=True)
def _stub(monkeypatch):
    monkeypatch.setattr(compose_mod, "get_location", lambda lid: _Loc())
    monkeypatch.setattr(compose_mod, "find_legal_parking_nearby", lambda *a, **k: [])
    monkeypatch.setattr(compose_mod, "API_BASE_URL", "https://api.example.com", raising=False)
    # links.py reads these at call time
    from app.monitor import links as links_mod
    monkeypatch.setattr(links_mod, "API_BASE_URL", "https://api.example.com")
    monkeypatch.setattr(links_mod, "APP_BASE_URL", "https://app.example.com")


def _watch(**kw):
    base = dict(
        watch_id="wch_abc123",
        manage_token="tok_secret_value_1234567890",
        location_id="w-grant-pl-500-north",
        start_time=NOW - timedelta(hours=2),
        end_time=NOW + timedelta(days=17),
    )
    base.update(kw)
    return Watch(**base)


def _legal_until_decision(later_dates=True):
    move_by = datetime(2026, 9, 10, 9, 0, tzinfo=CHICAGO_TZ)
    reasons = [
        DecisionReason(category="residential", verdict="allows",
                       detail="No residential parking permit is required on this block."),
        DecisionReason(
            category="street_cleaning", verdict="limits",
            detail="Street cleaning begins Thu Sep 10 9 AM, before your requested departure.",
        ),
    ]
    if later_dates:
        reasons.append(DecisionReason(
            category="street_cleaning", verdict="limits",
            detail="Street cleaning begins Mon Sep 14 9 AM, before your requested departure.",
        ))
    reasons.append(DecisionReason(category="temporary_closure", verdict="allows",
                                  detail="No temporary street-closure permit affects this block."))
    return ParkingDecision(
        status=ParkingStatus.LEGAL_UNTIL,
        move_by=move_by,
        reasons=reasons,
        start_time_display="Tuesday, September 8, 2026 at 6:00 AM",
        end_time_display="Friday, September 25, 2026 at 12:00 AM",
        move_by_display="Thursday, September 10, 2026 at 9:00 AM",
    )


def _not_legal_decision():
    return ParkingDecision(
        status=ParkingStatus.NOT_LEGAL,
        reasons=[
            DecisionReason(
                category="residential", verdict="blocks",
                detail=("Residential zone 100 permit required to park here; you have no permit. "
                        "(Posted hours are not in the City dataset; the zone is treated as in "
                        "effect for your interval.)"),
            ),
            DecisionReason(category="street_cleaning", verdict="allows",
                           detail="No street cleaning scheduled during your interval."),
            DecisionReason(category="temporary_closure", verdict="allows",
                           detail="No temporary street-closure permit affects this block."),
        ],
        start_time_display="Wednesday, September 2, 2026 at 10:00 AM",
        end_time_display="Thursday, September 3, 2026 at 10:00 AM",
        urgent_alert=True,
        urgent_reason="A verified restriction prevents parking here for this request.",
    )


# --- structure / MIME ------------------------------------------------

def test_daily_legal_until_html_and_text():
    email = compose_email(_watch(), _legal_until_decision(), MessageType.MORNING)
    assert email.subject == "🚗 Parking update: Move by Sep 10 at 9:00 AM"

    h, t = email.body_html, email.body_text
    assert h and t
    # real HTML hierarchy, not Markdown
    assert "<h1" in h and "<h2" in h and "<strong>" in h and "<hr" in h
    assert "##" not in h and "**" not in h
    assert "<" not in t and "##" not in t and "**" not in t
    # deterministic move-by wording, verbatim
    assert "Thursday, September 10, 2026 at 9:00 AM" in h
    assert "LEGAL UNTIL" in h


def test_no_duplicate_explanation_block():
    """The old format printed a machine STATUS/[ok]/[!] block and then a second
    full agent explanation. Neither should recur."""
    email = compose_email(
        _watch(), _legal_until_decision(), MessageType.MORNING,
        agent_prose="## Status\n**Move by 9 AM.** The north side has the same restriction.",
    )
    t = email.body_text
    assert "[ok]" not in t and "[!]" not in t         # no machine reason markers
    assert "##" not in t and "**" not in t            # agent markdown stripped
    assert "north side has the same restriction" in t
    # the deterministic explanation is not repeated by a second agent block
    assert t.count("This is the first restriction that affects your stay.") == 1
    assert t.count("rules-based system using") == 1


def test_earliest_move_by_restriction_emphasized():
    email = compose_email(_watch(), _legal_until_decision(later_dates=True), MessageType.MORNING)
    t = email.body_text
    # the Sep 10 restriction (the one that sets move_by) is shown and flagged
    assert "Sep 10" in t
    assert "This is the first restriction that affects your stay." in t
    # later windows are summarized, never dumped one by one
    assert "Sep 14" not in t
    assert "do not change your earliest move-by time" in t


def test_urgent_email_template():
    email = compose_email(_watch(), _not_legal_decision(), MessageType.URGENT)
    assert email.subject == "🚨 Urgent parking alert: Move your car now"
    h = email.body_html
    assert "Time-Sensitive Parking Alert" in h
    assert "NOT LEGAL" in h
    assert "Residential zone 100 permit required" in h
    # the dataset caveat is demoted to the smaller secondary style, not the headline
    assert "Posted hours are not in the City dataset" in h
    assert "#6b7280" in h  # muted colour used for the caveat span


def test_daily_fully_legal():
    d = ParkingDecision(
        status=ParkingStatus.LEGAL,
        reasons=[DecisionReason(category="residential", verdict="allows",
                                detail="No residential parking permit is required on this block.")],
        start_time_display="A", end_time_display="B",
    )
    email = compose_email(_watch(), d, MessageType.MORNING)
    assert email.subject == "✅ Daily parking check: You're still clear"
    assert "LEGAL" in email.body_html
    assert "Move your car by" not in email.body_html


# --- unsubscribe / manage links ------------------------------------

def test_daily_email_has_working_unsubscribe_link():
    email = compose_email(_watch(), _legal_until_decision(), MessageType.MORNING)
    url = "https://api.example.com/api/watches/wch_abc123/unsubscribe?token=tok_secret_value_1234567890"
    assert f'href="{url}"' in email.body_html
    assert url in email.body_text
    assert "Stop monitoring this parking spot" in email.body_html


def test_urgent_email_has_working_unsubscribe_link():
    email = compose_email(_watch(), _not_legal_decision(), MessageType.URGENT)
    path = "/api/watches/wch_abc123/unsubscribe?token=tok_secret_value_1234567890"
    assert path in email.body_html
    assert "/api/watches/wch_abc123/unsubscribe?token=" in email.body_text


def test_footer_has_all_three_management_links_capability_gated():
    for decision, msg in (
        (_legal_until_decision(), MessageType.MORNING),
        (_not_legal_decision(), MessageType.URGENT),
    ):
        email = compose_email(_watch(), decision, msg)
        for label in ("Extend parking time", "Change parking spot",
                      "Stop monitoring this parking spot"):
            assert label in email.body_html
            assert label in email.body_text
        # the extend link is a plain deep link into the app (opening it mutates
        # nothing) and carries the capability token; text fallback keeps it raw
        extend = (
            "https://app.example.com/?manage=wch_abc123"
            "&token=tok_secret_value_1234567890&action=extend"
        )
        assert extend in email.body_text
        # in HTML the & is attribute-escaped
        assert "manage=wch_abc123&amp;token=tok_secret_value_1234567890&amp;action=extend" in (
            email.body_html
        )


def test_link_dynamic_values_cannot_break_the_attribute():
    w = _watch(watch_id="wch_x", manage_token='a b"<c>')
    html = compose_email(w, _not_legal_decision(), MessageType.URGENT).body_html
    assert 'a b"<c>' not in html                        # raw chars never land in the href
    assert "%22%3Cc%3E" in html                         # " < > percent-encoded in the URL


def test_reason_detail_is_html_escaped():
    d = _not_legal_decision()
    d.reasons[0].detail = "Zone <script>alert(1)</script> & permit required"
    email = compose_email(_watch(), d, MessageType.URGENT)
    assert "<script>alert(1)</script>" not in email.body_html
    assert "&lt;script&gt;" in email.body_html


def test_nearby_language_only_when_investigated(monkeypatch):
    # LEGAL -> no investigation, no nearby section
    d = ParkingDecision(
        status=ParkingStatus.LEGAL,
        reasons=[DecisionReason(category="residential", verdict="allows", detail="ok.")],
        start_time_display="A", end_time_display="B",
    )
    assert "Nearby parking" not in compose_email(_watch(), d, MessageType.MORNING).body_html

    # LEGAL_UNTIL -> deterministic nearby search ran (even if it found nothing)
    html = compose_email(_watch(), _legal_until_decision(), MessageType.MORNING).body_html
    assert "Nearby parking" in html
