import json
from datetime import datetime, timedelta

from app.config import CHICAGO_TZ
from app.monitor.models import Watch, WatchStatus
from app.monitor.store import FileWatchStore
from app.services import email as email_mod


def test_file_store_round_trip(tmp_path):
    store = FileWatchStore(tmp_path / "watches.json")
    assert store.load() == {}

    w = Watch(
        location_id="x",
        start_time=datetime(2026, 9, 8, 19, tzinfo=CHICAGO_TZ),
        end_time=datetime(2026, 9, 9, 9, tzinfo=CHICAGO_TZ),
        notified=["morning:2026-09-08"],
        last_decision="LEGAL",
    )
    store.save({w.watch_id: w})

    back = FileWatchStore(tmp_path / "watches.json").load()
    assert list(back) == [w.watch_id]
    assert back[w.watch_id].last_decision == "LEGAL"
    assert back[w.watch_id].status is WatchStatus.ACTIVE

    # the serialized file must not contain an email field anywhere
    assert "email" not in (tmp_path / "watches.json").read_text().lower()


def test_email_falls_back_to_outbox(tmp_path, monkeypatch):
    monkeypatch.setattr(email_mod, "GMAIL_ADDRESS", None)
    monkeypatch.setattr(email_mod, "GMAIL_APP_PASSWORD", None)
    monkeypatch.setattr(email_mod, "OUTBOX_DIR", tmp_path / "outbox")

    result = email_mod.send_email("driver@example.com", "Test subject", "Body line.")
    assert result.endswith(".txt")
    written = (tmp_path / "outbox").glob("*.txt")
    content = next(written).read_text()
    assert "Subject: Test subject" in content
    assert "Body line." in content


def test_pre_existing_watch_without_manage_token_is_backfilled(tmp_path):
    """Watches created before manage_token existed must keep working: the model
    mints one, and the store persists it once so it is stable thereafter."""
    path = tmp_path / "watches.json"
    path.write_text(json.dumps({
        "wch_old": {
            "watch_id": "wch_old",
            "location_id": "x",
            "start_time": "2026-09-08T19:00:00-05:00",
            "end_time": "2026-09-20T09:00:00-05:00",
            "status": "active",
            "notified": ["morning:2026-09-08"],
        }
    }))

    loaded = FileWatchStore(path).load()                 # must not raise
    w = loaded["wch_old"]
    assert w.manage_token and len(w.manage_token) >= 20
    assert w.notified == ["morning:2026-09-08"]          # untouched
    assert w.status is WatchStatus.ACTIVE

    on_disk = json.loads(path.read_text())["wch_old"]
    assert on_disk["manage_token"] == w.manage_token     # persisted once
    # a second load reads the same token and does not rewrite
    assert FileWatchStore(path).load()["wch_old"].manage_token == w.manage_token


def test_watch_not_active_after_end(tmp_path):
    now = datetime(2026, 9, 10, 12, tzinfo=CHICAGO_TZ)
    w = Watch(
        location_id="x",
        start_time=now - timedelta(days=2),
        end_time=now - timedelta(hours=1),
    )
    assert w.is_active(now) is False
