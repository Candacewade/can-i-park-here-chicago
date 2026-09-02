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
        return {
            wid: Watch.model_validate(row)
            for wid, row in self._backend.load().items()
        }

    def save(self, watches: dict[str, Watch]) -> None:
        self._backend.save(
            {wid: w.model_dump(mode="json") for wid, w in sorted(watches.items())}
        )


def FileWatchStore(path: Path | None = None) -> WatchStore:
    return WatchStore(FileJsonStore(path or (LOCAL_DATA_DIR / WATCHES_DATA_NAME)))


def get_store() -> WatchStore:
    return WatchStore()
