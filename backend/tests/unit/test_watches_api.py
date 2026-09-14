from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main
from app.config import CHICAGO_TZ
from app.models.decision import ParkingDecision, ParkingStatus
from app.monitor.models import Watch, WatchStatus

client = TestClient(api_main.app)


class MemStore:
    def __init__(self):
        self.w: dict[str, Watch] = {}
        self.saves = 0

    def load(self):
        return self.w

    def save(self, watches):
        self.saves += 1
        self.w = watches


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    store = MemStore()
    notify_map: dict[str, str] = {}
    monkeypatch.setattr(api_main, "get_store", lambda: store)
    monkeypatch.setattr(
        api_main.notify, "register_email",
        lambda wid, email: (notify_map.__setitem__(wid, email), True)[1],
    )
    monkeypatch.setattr(api_main.notify, "forget", lambda wid: notify_map.pop(wid, None))
    monkeypatch.setattr(api_main.notify, "get_email", lambda wid: notify_map.get(wid))
    monkeypatch.setattr(
        api_main.notify, "find_watch_ids_for_email",
        lambda email: {
            wid for wid, e in notify_map.items() if e.strip().lower() == email.strip().lower()
        },
    )
    store.notify_map = notify_map
    return store


def _payload(**kw):
    start = datetime.now(tz=CHICAGO_TZ) + timedelta(hours=1)
    base = {
        "location_id": "wrightwood-3300w-north",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=14)).isoformat(),
        "email": "driver@example.com",
    }
    base.update(kw)
    return base


def _create(**kw):
    r = client.post("/api/watches", json=_payload(**kw))
    assert r.status_code == 201, r.text
    return r.json()


# --- create -----------------------------------------------------------

def test_create_returns_manage_token(_mem):
    body = _create()
    assert body["watch_id"].startswith("wch_")
    assert body["manage_token"] and len(body["manage_token"]) >= 20
    assert body["email_registered"] is True
    assert _mem.notify_map[body["watch_id"]] == "driver@example.com"


def test_create_rejects_unknown_location(_mem):
    assert client.post("/api/watches", json=_payload(location_id="nowhere")).status_code == 422


def test_create_rejects_bad_email(_mem):
    assert client.post("/api/watches", json=_payload(email="not-an-email")).status_code == 422


def test_create_same_email_same_spot_replaces_not_duplicates(_mem):
    """Regression: a second POST for the same email + same spot (double-click,
    retry, a second browser/device) used to leave TWO active watches, each
    emailing independently -> multiple near-identical daily emails."""
    first = _create()
    second = _create()  # same default email + location_id as `first`

    assert first["watch_id"] != second["watch_id"]
    assert _mem.w[first["watch_id"]].status is WatchStatus.RESOLVED
    assert _mem.w[second["watch_id"]].status is WatchStatus.ACTIVE
    # only the surviving watch is registered for email
    assert first["watch_id"] not in _mem.notify_map
    assert _mem.notify_map[second["watch_id"]] == "driver@example.com"
    active = [w for w in _mem.w.values() if w.status is WatchStatus.ACTIVE]
    assert len(active) == 1


def test_create_same_email_different_spot_is_not_deduped(_mem):
    """Watching two different spots with the same email is legitimate (e.g.
    two cars) and must not collapse into one watch."""
    first = _create()
    second = _create(location_id="george-3200w-north")

    assert _mem.w[first["watch_id"]].status is WatchStatus.ACTIVE
    assert _mem.w[second["watch_id"]].status is WatchStatus.ACTIVE
    assert len(_mem.w) == 2


def test_create_different_email_same_spot_is_not_deduped(_mem):
    a = _create(email="a@example.com")
    b = _create(email="b@example.com")
    assert _mem.w[a["watch_id"]].status is WatchStatus.ACTIVE
    assert _mem.w[b["watch_id"]].status is WatchStatus.ACTIVE
    assert len(_mem.w) == 2


# --- "find my watches" by email (not verified -- user's explicit choice
# after the emailed-verification-link version wasn't delivering reliably) ---

def test_by_email_lists_only_active_watches_for_that_address(_mem):
    mine = _create(email="driver@example.com")
    other = _create(email="someone-else@example.com")
    # a different location_id -- otherwise the same-email-same-spot dedup
    # (POST /api/watches) would resolve `mine` when this one is created
    stopped = _create(email="driver@example.com", location_id="george-3200w-north")
    client.delete(f"/api/watches/{stopped['watch_id']}?token={stopped['manage_token']}")

    r = client.get("/api/watches/by-email?email=driver@example.com")
    assert r.status_code == 200
    ids = {w["watch_id"] for w in r.json()["watches"]}
    assert ids == {mine["watch_id"]}
    assert other["watch_id"] not in ids
    assert stopped["watch_id"] not in ids

    item = r.json()["watches"][0]
    assert item["manage_token"] == mine["manage_token"]  # needed to act on it
    assert "email" not in item


def test_by_email_matches_case_insensitively(_mem):
    mine = _create(email="Driver@Example.com")
    r = client.get("/api/watches/by-email?email=driver@example.com")
    assert {w["watch_id"] for w in r.json()["watches"]} == {mine["watch_id"]}


def test_by_email_empty_for_address_with_no_watches(_mem):
    r = client.get("/api/watches/by-email?email=nobody@example.com")
    assert r.status_code == 200
    assert r.json()["watches"] == []


def test_by_email_requires_the_email_param(_mem):
    assert client.get("/api/watches/by-email").status_code == 422
    assert client.get("/api/watches/by-email?email=").status_code == 422


def test_extend_and_stop_work_with_the_email_lookup_watch_and_token(_mem, _stub_eval):
    """The manage_token handed back by /by-email is a real, usable token --
    same extend/stop endpoints a single-watch email link would use."""
    watch = _create(email="driver@example.com")
    item = client.get("/api/watches/by-email?email=driver@example.com").json()["watches"][0]

    new_end = _mem.w[watch["watch_id"]].end_time + timedelta(days=1)
    r = client.post(
        f"/api/watches/{item['watch_id']}/extend",
        json={"token": item["manage_token"], "end_time": new_end.isoformat()},
    )
    assert r.status_code == 200

    d = client.delete(f"/api/watches/{item['watch_id']}?token={item['manage_token']}")
    assert d.status_code == 200 and d.json()["status"] == "resolved"


# --- read / delete are token-gated ----------------------------------

def test_get_and_delete_require_the_token(_mem):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]

    assert client.get(f"/api/watches/{wid}").status_code == 404          # no token
    assert client.get(f"/api/watches/{wid}?token=wrong").status_code == 404

    g = client.get(f"/api/watches/{wid}?token={tok}")
    assert g.status_code == 200
    assert "email" not in g.json()
    assert g.json()["status"] == "active"
    # display helpers let a fresh device (email link, empty localStorage) render
    # the monitor card without another parking search
    assert g.json()["through_display"]
    assert "location_summary" in g.json()

    assert client.delete(f"/api/watches/{wid}?token=wrong").status_code == 404
    d = client.delete(f"/api/watches/{wid}?token={tok}")
    assert d.status_code == 200 and d.json()["status"] == "resolved"
    assert wid not in _mem.notify_map


def test_get_missing_watch_404(_mem):
    assert client.get("/api/watches/wch_nope?token=x").status_code == 404


def test_get_resolved_watch_still_readable_so_client_can_clear(_mem):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]
    client.delete(f"/api/watches/{wid}?token={tok}")
    g = client.get(f"/api/watches/{wid}?token={tok}")
    assert g.status_code == 200
    assert g.json()["status"] == "resolved"   # frontend sees this -> drops localStorage


# --- unsubscribe: GET shows a page, POST does the work --------------

def test_unsubscribe_GET_does_not_mutate(_mem):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]

    r = client.get(f"/api/watches/{wid}/unsubscribe?token={tok}")
    assert r.status_code == 200
    assert "Stop monitoring" in r.text and "<form" in r.text
    # nothing changed -- a scanner / prefetch of the link is harmless
    assert _mem.w[wid].status is WatchStatus.ACTIVE
    assert wid in _mem.notify_map


def test_unsubscribe_POST_resolves_and_forgets(_mem):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]

    r = client.post(f"/api/watches/{wid}/unsubscribe?token={tok}")
    assert r.status_code == 200
    assert "turned off" in r.text.lower()
    assert _mem.w[wid].status is WatchStatus.RESOLVED
    assert wid not in _mem.notify_map

    # idempotent
    assert client.post(f"/api/watches/{wid}/unsubscribe?token={tok}").status_code == 200


def test_unsubscribe_bad_token_cannot_resolve(_mem):
    body = _create()
    wid = body["watch_id"]
    assert client.get(f"/api/watches/{wid}/unsubscribe?token=nope").status_code == 404
    assert client.post(f"/api/watches/{wid}/unsubscribe?token=nope").status_code == 404
    assert client.post(f"/api/watches/{wid}/unsubscribe").status_code == 404   # no token
    assert _mem.w[wid].status is WatchStatus.ACTIVE
    assert wid in _mem.notify_map


def test_unsubscribe_cannot_touch_another_watch(_mem):
    a = _create(email="a@example.com")
    b = _create(email="b@example.com")
    # a's token must not unsubscribe b, via GET or POST
    assert client.get(
        f"/api/watches/{b['watch_id']}/unsubscribe?token={a['manage_token']}"
    ).status_code == 404
    assert client.post(
        f"/api/watches/{b['watch_id']}/unsubscribe?token={a['manage_token']}"
    ).status_code == 404
    assert _mem.w[b["watch_id"]].status is WatchStatus.ACTIVE
    assert b["watch_id"] in _mem.notify_map


# --- replace (change parking spot) ---------------------------------

def test_replace_resolves_old_and_activates_new(_mem):
    old = _create()
    old_id, tok = old["watch_id"], old["manage_token"]

    start = datetime.now(tz=CHICAGO_TZ) + timedelta(hours=2)
    r = client.post(
        f"/api/watches/{old_id}/replace",
        json={
            "token": tok,
            "location_id": "wrightwood-3300w-north",
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()
    new_id = out["watch_id"]
    assert out["old_watch_id"] == old_id
    assert new_id != old_id
    assert out["email_registered"] is True

    assert _mem.w[old_id].status is WatchStatus.RESOLVED
    assert _mem.w[new_id].status is WatchStatus.ACTIVE
    # recipient carried over, old mapping dropped
    assert _mem.notify_map.get(new_id) == "driver@example.com"
    assert old_id not in _mem.notify_map
    # fresh dedup history
    assert _mem.w[new_id].notified == []


def test_replace_can_reuse_or_override_email(_mem):
    old = _create(email="old@example.com")
    start = datetime.now(tz=CHICAGO_TZ) + timedelta(hours=2)
    r = client.post(
        f"/api/watches/{old['watch_id']}/replace",
        json={
            "token": old["manage_token"],
            "location_id": "wrightwood-3300w-north",
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(days=1)).isoformat(),
            "email": "new@example.com",
        },
    )
    assert r.status_code == 200
    assert _mem.notify_map[r.json()["watch_id"]] == "new@example.com"


def test_replace_bad_token_rejected_and_nothing_changes(_mem):
    old = _create()
    start = datetime.now(tz=CHICAGO_TZ) + timedelta(hours=2)
    r = client.post(
        f"/api/watches/{old['watch_id']}/replace",
        json={
            "token": "wrong",
            "location_id": "wrightwood-3300w-north",
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 404
    assert _mem.w[old["watch_id"]].status is WatchStatus.ACTIVE
    assert len(_mem.w) == 1


def test_replace_unknown_new_location_leaves_old_active(_mem):
    old = _create()
    start = datetime.now(tz=CHICAGO_TZ) + timedelta(hours=2)
    r = client.post(
        f"/api/watches/{old['watch_id']}/replace",
        json={
            "token": old["manage_token"],
            "location_id": "nowhere",
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 422
    assert _mem.w[old["watch_id"]].status is WatchStatus.ACTIVE
    assert len(_mem.w) == 1  # no second watch created


# --- extend parking time ------------------------------------------

@pytest.fixture
def _stub_eval(monkeypatch):
    """Deterministic engine + City data stubbed; the test controls the verdict."""
    box = {"status": ParkingStatus.LEGAL, "move_by_display": None,
           "urgent_alert": False, "urgent_reason": None}
    monkeypatch.setattr(api_main, "gather_evidence", lambda req: object())
    monkeypatch.setattr(
        api_main, "evaluate_parking",
        lambda req, ev: ParkingDecision(
            status=box["status"], move_by_display=box["move_by_display"],
            urgent_alert=box["urgent_alert"], urgent_reason=box["urgent_reason"],
            start_time_display="S", end_time_display="E",
        ),
    )
    return box


def _extend(wid, token, end_dt):
    return client.post(
        f"/api/watches/{wid}/extend",
        json={"token": token, "end_time": end_dt.isoformat()},
    )


def test_extend_pushes_end_time_and_re_evaluates(_mem, _stub_eval):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]
    before = _mem.w[wid]
    new_end = before.end_time + timedelta(days=12)

    _stub_eval["status"] = ParkingStatus.LEGAL_UNTIL
    _stub_eval["move_by_display"] = "Thursday, September 10, 2026 at 9:00 AM"

    r = _extend(wid, tok, new_end)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "LEGAL_UNTIL"
    assert out["move_by_display"] == "Thursday, September 10, 2026 at 9:00 AM"
    assert "move by" in out["summary"].lower()

    w = _mem.w[wid]
    assert w.end_time == new_end                          # persisted
    assert w.watch_id == before.watch_id                  # same identity
    assert w.manage_token == tok                          # unchanged
    assert w.location_id == before.location_id
    assert w.start_time == before.start_time
    assert w.permit_zone == before.permit_zone
    assert w.status is WatchStatus.ACTIVE
    assert _mem.notify_map[wid] == "driver@example.com"   # recipient untouched


def test_extend_requires_correct_token(_mem, _stub_eval):
    body = _create()
    wid = body["watch_id"]
    new_end = _mem.w[wid].end_time + timedelta(days=1)
    assert _extend(wid, "wrong", new_end).status_code == 404
    assert _mem.w[wid].end_time != new_end


def test_extend_another_watch_token_rejected(_mem, _stub_eval):
    a = _create(email="a@example.com")
    b = _create(email="b@example.com")
    new_end = _mem.w[b["watch_id"]].end_time + timedelta(days=1)
    assert _extend(b["watch_id"], a["manage_token"], new_end).status_code == 404


def test_extend_rejects_resolved_watch(_mem, _stub_eval):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]
    client.delete(f"/api/watches/{wid}?token={tok}")
    r = _extend(wid, tok, _mem.w[wid].end_time + timedelta(days=1))
    assert r.status_code == 409


def test_extend_rejects_end_not_later(_mem, _stub_eval):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]
    cur = _mem.w[wid].end_time
    assert _extend(wid, tok, cur).status_code == 422                    # equal
    assert _extend(wid, tok, cur - timedelta(hours=1)).status_code == 422  # earlier
    assert _mem.w[wid].end_time == cur


def test_extend_drops_reminder_keys_keeps_morning_and_urgent(_mem, _stub_eval):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]
    _mem.w[wid].notified = [
        "morning:2026-09-02", "urgent:abc12345", "reminder:3d", "reminder:night",
    ]

    _extend(wid, tok, _mem.w[wid].end_time + timedelta(days=10))

    assert set(_mem.w[wid].notified) == {"morning:2026-09-02", "urgent:abc12345"}


# --- self-reported override -----------------------------------------

def _override(wid, token, **kw):
    body = {
        "token": token,
        "status": "NOT_LEGAL",
        "note": "Orange street cleaning sign posted, not in the app's data",
        "expires_at": (datetime.now(tz=CHICAGO_TZ) + timedelta(days=1)).isoformat(),
    }
    body.update(kw)
    return client.post(f"/api/watches/{wid}/override", json=body)


def test_set_override_returns_the_overridden_status(_mem, _stub_eval):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]

    r = _override(wid, tok)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "NOT_LEGAL"
    assert out["override"]["note"].startswith("Orange street cleaning sign")
    assert _mem.w[wid].override is not None
    assert _mem.w[wid].override.status == ParkingStatus.NOT_LEGAL


def test_set_override_legal_until_requires_move_by(_mem, _stub_eval):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]
    move_by = (datetime.now(tz=CHICAGO_TZ) + timedelta(hours=5)).isoformat()

    ok = _override(wid, tok, status="LEGAL_UNTIL", move_by=move_by)
    assert ok.status_code == 200, ok.text
    assert ok.json()["override"]["move_by_display"]

    missing = _override(wid, tok, status="LEGAL_UNTIL", move_by=None)
    assert missing.status_code == 422


def test_set_override_rejects_unknown_status(_mem, _stub_eval):
    body = _create()
    r = _override(body["watch_id"], body["manage_token"], status="UNKNOWN")
    assert r.status_code == 422


def test_set_override_rejects_past_expiry(_mem, _stub_eval):
    body = _create()
    past = (datetime.now(tz=CHICAGO_TZ) - timedelta(hours=1)).isoformat()
    r = _override(body["watch_id"], body["manage_token"], expires_at=past)
    assert r.status_code == 422


def test_set_override_requires_correct_token(_mem, _stub_eval):
    body = _create()
    r = _override(body["watch_id"], "wrong-token")
    assert r.status_code == 404
    assert _mem.w[body["watch_id"]].override is None


def test_set_override_rejects_resolved_watch(_mem, _stub_eval):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]
    client.delete(f"/api/watches/{wid}?token={tok}")
    assert _override(wid, tok).status_code == 409


def test_get_watch_reflects_active_override(_mem, _stub_eval):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]
    _override(wid, tok)

    view = client.get(f"/api/watches/{wid}?token={tok}").json()
    assert view["override"]["status"] == "NOT_LEGAL"


def test_clear_override_reverts_to_city_data(_mem, _stub_eval):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]
    _override(wid, tok)

    r = client.delete(f"/api/watches/{wid}/override?token={tok}")
    assert r.status_code == 200
    assert r.json()["override"] is None
    assert _mem.w[wid].override is None

    # idempotent -- clearing again doesn't error
    assert client.delete(f"/api/watches/{wid}/override?token={tok}").status_code == 200


def test_clear_override_requires_correct_token(_mem, _stub_eval):
    body = _create()
    wid, tok = body["watch_id"], body["manage_token"]
    _override(wid, tok)
    assert client.delete(f"/api/watches/{wid}/override?token=wrong").status_code == 404
    assert _mem.w[wid].override is not None


def test_monitor_run_endpoint(monkeypatch, _mem):
    async def fake_run(use_agent):
        from app.monitor.run import MonitorReport
        return MonitorReport(ran_at=datetime.now(tz=CHICAGO_TZ), checked=0, emails_sent=0)

    monkeypatch.setattr(api_main, "run_monitor", fake_run)
    monkeypatch.setattr(api_main, "MONITOR_TOKEN", None)
    r = client.post("/api/monitor/run")
    assert r.status_code == 200
    assert r.json()["checked"] == 0
