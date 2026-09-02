from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main
from app.config import CHICAGO_TZ
from app.monitor.models import Watch

client = TestClient(api_main.app)


class MemStore:
    def __init__(self):
        self.w: dict[str, Watch] = {}

    def load(self):
        return self.w

    def save(self, watches):
        self.w = watches


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    store = MemStore()
    monkeypatch.setattr(api_main, "get_store", lambda: store)
    monkeypatch.setattr(api_main.notify, "register_email", lambda wid, email: True)
    monkeypatch.setattr(api_main.notify, "forget", lambda wid: None)
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


def test_create_get_delete_watch(_mem):
    r = client.post("/api/watches", json=_payload())
    assert r.status_code == 201
    wid = r.json()["watch_id"]
    assert wid.startswith("wch_")
    assert r.json()["email_registered"] is True

    g = client.get(f"/api/watches/{wid}")
    assert g.status_code == 200
    assert "email" not in g.json()  # never echoed
    assert g.json()["status"] == "active"

    d = client.delete(f"/api/watches/{wid}")
    assert d.status_code == 200
    assert d.json()["status"] == "resolved"


def test_create_rejects_unknown_location(_mem):
    r = client.post("/api/watches", json=_payload(location_id="nowhere"))
    assert r.status_code == 422


def test_create_rejects_bad_email(_mem):
    r = client.post("/api/watches", json=_payload(email="not-an-email"))
    assert r.status_code == 422


def test_get_missing_watch_404(_mem):
    assert client.get("/api/watches/wch_nope").status_code == 404


def test_monitor_run_endpoint(monkeypatch, _mem):
    async def fake_run(use_agent):
        from app.monitor.run import MonitorReport
        return MonitorReport(ran_at=datetime.now(tz=CHICAGO_TZ), checked=0, emails_sent=0)

    monkeypatch.setattr(api_main, "run_monitor", fake_run)
    monkeypatch.setattr(api_main, "MONITOR_TOKEN", None)
    r = client.post("/api/monitor/run")
    assert r.status_code == 200
    assert r.json()["checked"] == 0
