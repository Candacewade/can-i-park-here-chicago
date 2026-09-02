from __future__ import annotations

import pytest

from app.services.socrata import SocrataError


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path, monkeypatch):
    """Keep the test suite from touching any real runtime user-data store."""
    import app.json_store as js
    from app.json_store import FileJsonStore
    from app.locations import registry

    monkeypatch.setattr(js, "GH_DATA_REPO", None)
    monkeypatch.setattr(js, "GH_DATA_TOKEN", None)
    monkeypatch.setattr(js, "LOCAL_DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(
        registry, "_blocks_store", lambda: FileJsonStore(tmp_path / "data" / "blocks.json")
    )
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
