"""watch_id -> notification destination. This is where the PII lives.

Production: the ``WATCH_NOTIFY_MAP`` env var (a JSON object), held as a GitHub
Actions secret and never committed. Local dev: a git-ignored JSON file that the
API may also write when someone registers a watch.
"""

from __future__ import annotations

import json

from app.config import NOTIFY_MAP_LOCAL_FILE, WATCH_NOTIFY_MAP


def _load_map() -> dict[str, dict]:
    combined: dict[str, dict] = {}
    if NOTIFY_MAP_LOCAL_FILE.exists():
        try:
            combined.update(json.loads(NOTIFY_MAP_LOCAL_FILE.read_text() or "{}"))
        except (ValueError, OSError):
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
    """Best-effort: write to the local map file. Returns False if not writable
    (e.g. on Render) -- the operator then adds the entry to the secret."""
    try:
        current: dict[str, dict] = {}
        if NOTIFY_MAP_LOCAL_FILE.exists():
            current = json.loads(NOTIFY_MAP_LOCAL_FILE.read_text() or "{}")
        current[watch_id] = {"email": email}
        NOTIFY_MAP_LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        NOTIFY_MAP_LOCAL_FILE.write_text(json.dumps(current, indent=2) + "\n")
        return True
    except OSError:
        return False


def forget(watch_id: str) -> None:
    try:
        if NOTIFY_MAP_LOCAL_FILE.exists():
            current = json.loads(NOTIFY_MAP_LOCAL_FILE.read_text() or "{}")
            current.pop(watch_id, None)
            NOTIFY_MAP_LOCAL_FILE.write_text(json.dumps(current, indent=2) + "\n")
    except (ValueError, OSError):
        pass
