from __future__ import annotations

import pytest

from app.services.socrata import SocrataError


@pytest.fixture(autouse=True)
def _isolate_blocks_registry(tmp_path, monkeypatch):
    """Keep the test suite from writing to the real backend/app/locations/blocks.json."""
    from app.json_store import FileJsonStore
    from app.locations import registry

    monkeypatch.setattr(registry, "_blocks_store", lambda: FileJsonStore(tmp_path / "blocks.json"))
    registry.reset_cache()
    yield
    registry.reset_cache()


class FakeSocrataClient:
    """Stand-in for SocrataClient: returns canned rows or raises SocrataError."""

    def __init__(self, rows=None, error: str | None = None):
        self._rows = rows or []
        self._error = error
        self.calls: list[tuple[str, dict]] = []

    def get_rows(self, dataset_id: str, params: dict[str, str]) -> list[dict]:
        self.calls.append((dataset_id, params))
        if self._error is not None:
            raise SocrataError(self._error)
        return self._rows

    def query_url(self, dataset_id: str, params: dict[str, str]) -> str:
        return f"https://example.test/{dataset_id}.json"
