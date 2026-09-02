"""Build the management links that go into monitoring emails.

Every link carries the watch's opaque ``manage_token`` as its credential -- never
the raw ``watch_id`` alone -- so knowing or guessing an id grants nothing.
"""

from __future__ import annotations

from urllib.parse import urlencode

from app.config import API_BASE_URL, APP_BASE_URL
from app.monitor.models import Watch


def unsubscribe_url(watch: Watch) -> str:
    """GET link that resolves this one watch and drops its notification mapping."""
    q = urlencode({"token": watch.manage_token})
    return f"{API_BASE_URL}/api/watches/{watch.watch_id}/unsubscribe?{q}"


def change_spot_url(watch: Watch) -> str:
    """Deep link back into the app to move the monitored spot (resolve old +
    create new). The mutation itself is POST /api/watches/{id}/replace."""
    base = APP_BASE_URL or ""
    q = urlencode({"manage": watch.watch_id, "token": watch.manage_token})
    return f"{base}/?{q}"
