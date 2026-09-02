"""Persistence for watches -- $0, no database, **never in the public repo**.

A thin typed wrapper over ``app.json_store.data_store`` (the private data repo in
production, a git-ignored local file otherwise). Watch rows carry anonymous ids +
state only -- the email lives in the notify map.
"""

from __future__ import annotations

from pathlib import Path

from app.config import LOCAL_DATA_DIR, WATCHES_DATA_NAME
from app.json_store import FileJsonStore, data_store
from app.monitor.models import Watch


class WatchStore:
    def __init__(self, backend=None) -> None:
        self._backend = backend or data_store(WATCHES_DATA_NAME)

    def load(self) -> dict[str, Watch]:
        raw = self._backend.load()
        watches = {wid: Watch.model_validate(row) for wid, row in raw.items()}
        # One-time, self-healing migration: watches created before manage_token
        # existed get one minted by the model default; persist it once so every
        # later read (and every email management link) sees the same value.
        if any(not row.get("manage_token") for row in raw.values()):
            self.save(watches)
        return watches

    def save(self, watches: dict[str, Watch]) -> None:
        self._backend.save(
            {wid: w.model_dump(mode="json") for wid, w in sorted(watches.items())}
        )


def FileWatchStore(path: Path | None = None) -> WatchStore:
    return WatchStore(FileJsonStore(path or (LOCAL_DATA_DIR / WATCHES_DATA_NAME)))


def get_store() -> WatchStore:
    return WatchStore()
