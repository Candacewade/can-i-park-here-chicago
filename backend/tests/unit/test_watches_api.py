from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main
from app.config import CHICAGO_TZ
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

    assert client.delete(f"/api/watches/{wid}?token=wrong").status_code == 404
    d = client.delete(f"/api/watches/{wid}?token={tok}")
    assert d.status_code == 200 and d.json()["status"] == "resolved"
    assert wid not in _mem.notify_map


def test_get_missing_watch_404(_mem):
    assert client.get("/api/watches/wch_nope?token=x").status_code == 404


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


def test_monitor_run_endpoint(monkeypatch, _mem):
    async def fake_run(use_agent):
        from app.monitor.run import MonitorReport
        return MonitorReport(ran_at=datetime.now(tz=CHICAGO_TZ), checked=0, emails_sent=0)

    monkeypatch.setattr(api_main, "run_monitor", fake_run)
    monkeypatch.setattr(api_main, "MONITOR_TOKEN", None)
    r = client.post("/api/monitor/run")
    assert r.status_code == 200
    assert r.json()["checked"] == 0
