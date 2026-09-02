"""watch_id -> notification destination (the email). User data.

Stored in the **private data repo** (``notify_map.json``) via the Contents API,
or a git-ignored local file in dev. An optional ``WATCH_NOTIFY_MAP`` env secret is
merged on top (seed / override). Never in the public code repo.
"""

from __future__ import annotations

import json

from app.config import NOTIFY_DATA_NAME, WATCH_NOTIFY_MAP
from app.json_store import data_store


def _store():
    return data_store(NOTIFY_DATA_NAME)


def _load_map() -> dict[str, dict]:
    combined: dict[str, dict] = {}
    try:
        combined.update(_store().load())
    except Exception:
        pass
    if WATCH_NOTIFY_MAP:
        try:
            combined.update(json.loads(WATCH_NOTIFY_MAP))
        except ValueError:
            pass
    return combined


def get_email(watch_id: str) -> str | None:
    entry = _load_map().get(watch_id)
    return entry.get("email") if isinstance(entry, dict) else None


def register_email(watch_id: str, email: str) -> bool:
    """Persist watch_id -> {email} in the private data store. Returns False only
    if the write fails (the operator can then add it to WATCH_NOTIFY_MAP)."""
    try:
        store = _store()
        current = store.load()
        current[watch_id] = {"email": email}
        store.save(current)
        return True
    except Exception:
        return False


def forget(watch_id: str) -> None:
    try:
        store = _store()
        current = store.load()
        if current.pop(watch_id, None) is not None:
            store.save(current)
    except Exception:
        pass
