"""Ephemeral, application-controlled evidence store for a single agent run.

Since the 2026-09-01 revision the deterministic core evidence (residential,
street cleaning, temporary closures, winter snow route) is gathered fresh by
``rules.gather`` on every evaluation and is *not* kept here. This store holds
only the **optional** evidence the agent's investigation wing adds:

    weather     NWS snow/precip outlook
    snow_route  a 2-inch-route check the agent ran off-season
    events      nearby special-event context
    closure_detail  fuller permit rows for explaining an unusual result

Only the MCP tools write here, and they only write what they fetched. The agent
chooses which tools run and with what location/time args; it cannot inject or
edit evidence content.

No database: a process-local dict with a TTL and a size cap.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

WEATHER = "weather"
SNOW_ROUTE = "snow_route"
EVENTS = "events"
CLOSURE_DETAIL = "closure_detail"

# Categories that feed the rule engine (the rest are context for the agent only).
_VERDICT_RELEVANT = (WEATHER, SNOW_ROUTE, EVENTS)

_TTL_SECONDS = 1800.0
_MAX_RUNS = 256

_lock = threading.Lock()


@dataclass
class _Entry:
    args: dict
    evidence: object
    stored_at: float


@dataclass
class _Run:
    created_at: float
    entries: dict[str, _Entry] = field(default_factory=dict)


_runs: dict[str, _Run] = {}


def _evict_locked() -> None:
    now = time.monotonic()
    for rid in [r for r, run in _runs.items() if now - run.created_at > _TTL_SECONDS]:
        _runs.pop(rid, None)
    if len(_runs) > _MAX_RUNS:
        oldest = sorted(_runs, key=lambda r: _runs[r].created_at)[: len(_runs) - _MAX_RUNS]
        for rid in oldest:
            _runs.pop(rid, None)


def _norm_args(location_id: str, start: datetime | None, end: datetime | None) -> dict:
    args: dict = {"location_id": location_id}
    if start is not None:
        args["start"] = start
    if end is not None:
        args["end"] = end
    return args


def record(
    run_id: str,
    category: str,
    *,
    location_id: str,
    evidence: object,
    start: datetime | None = None,
    end: datetime | None = None,
) -> None:
    with _lock:
        _evict_locked()
        run = _runs.get(run_id)
        if run is None:
            run = _runs[run_id] = _Run(created_at=time.monotonic())
        run.entries[category] = _Entry(
            args=_norm_args(location_id, start, end),
            evidence=evidence,
            stored_at=time.monotonic(),
        )


def _get(run_id: str, category: str, expected_args: dict):
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            return None
        entry = run.entries.get(category)
    if entry is None or entry.args != expected_args:
        return None
    return entry.evidence


def get(run_id: str, category: str, *, location_id: str, start=None, end=None):
    return _get(run_id, category, _norm_args(location_id, start, end))


def verdict_relevant_evidence(
    run_id: str, *, location_id: str, start: datetime, end: datetime
) -> dict[str, object]:
    """The agent-added evidence categories the rule engine consumes, for this run
    + block + interval. Missing / mismatched entries are simply absent."""
    interval_args = _norm_args(location_id, start, end)
    out: dict[str, object] = {}
    for category in _VERDICT_RELEVANT:
        ev = _get(run_id, category, interval_args)
        if ev is not None:
            out[category] = ev
    return out


def clear(run_id: str) -> None:
    with _lock:
        _runs.pop(run_id, None)


def reset() -> None:
    """Test helper: wipe all runs."""
    with _lock:
        _runs.clear()
