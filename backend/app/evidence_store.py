"""Ephemeral, application-controlled evidence store for a single agent run.

Flow:

    agent calls an MCP evidence tool
        -> the tool fetches authoritative data and normalizes it
        -> the tool records that typed evidence here under (run_id, category)
    agent calls evaluate_parking_request
        -> the evaluator reads the stored evidence back (never from the agent)
        -> the completeness check sees which required categories are present

Only the MCP tools write here, and they only write what they themselves fetched
from the City portal. The agent chooses *which* tools run and with *what*
location/time arguments, but cannot inject or edit evidence content.

No database: a process-local dict with a TTL and a size cap. This state is
request-scoped and is meant to be lost on restart.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from app.models.evidence import (
    ParkingEvidence,
    ResidentialZoneEvidence,
    StreetCleaningEvidence,
    TemporaryClosureEvidence,
)

RESIDENTIAL = "residential"
STREET_CLEANING = "street_cleaning"
TEMPORARY_CLOSURE = "temporary_closure"

_TTL_SECONDS = 1800.0
_MAX_RUNS = 256

_lock = threading.Lock()


@dataclass
class _Entry:
    args: dict          # normalized args the tool was called with
    evidence: object    # a typed *Evidence model
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


def _get(
    run_id: str,
    category: str,
    *,
    location_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
):
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            return None
        entry = run.entries.get(category)
        if entry is None:
            return None
    # Evidence only counts if it was gathered for this exact block (+ interval).
    if entry.args != _norm_args(location_id, start, end):
        return None
    return entry.evidence


def build_bundle(
    run_id: str, *, location_id: str, start: datetime, end: datetime
) -> ParkingEvidence:
    """Assemble the evidence the evaluator will use. Missing/mismatched -> None."""
    res = _get(run_id, RESIDENTIAL, location_id=location_id)
    clean = _get(run_id, STREET_CLEANING, location_id=location_id, start=start, end=end)
    closure = _get(run_id, TEMPORARY_CLOSURE, location_id=location_id, start=start, end=end)
    return ParkingEvidence(
        residential=res if isinstance(res, ResidentialZoneEvidence) else None,
        street_cleaning=clean if isinstance(clean, StreetCleaningEvidence) else None,
        temporary_closure=closure if isinstance(closure, TemporaryClosureEvidence) else None,
    )


def clear(run_id: str) -> None:
    with _lock:
        _runs.pop(run_id, None)


def reset() -> None:
    """Test helper: wipe all runs."""
    with _lock:
        _runs.clear()
