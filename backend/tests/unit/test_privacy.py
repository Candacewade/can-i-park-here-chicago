"""Runtime user data must never live in the public code repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app import json_store
from app.json_store import FileJsonStore, GitHubJsonStore, data_store

REPO_ROOT = Path(__file__).resolve().parents[3]

_FORBIDDEN = [
    "backend/watches.json",
    "backend/app/locations/blocks.json",
    "backend/notify_map.json",
    "backend/notify_map.local.json",
]


def _tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return set(out.stdout.split())


def test_no_user_data_files_are_committed():
    tracked = _tracked_files()
    leaked = [p for p in _FORBIDDEN if p in tracked]
    assert not leaked, f"user-data files committed to the public repo: {leaked}"
    # nothing under a .data/ dir either
    assert not any(p.startswith("backend/.data/") for p in tracked)


def test_gitignore_covers_the_data_dir():
    ignore = (REPO_ROOT / ".gitignore").read_text()
    assert "backend/.data/" in ignore


def test_data_store_uses_private_repo_when_configured(monkeypatch):
    monkeypatch.setattr(json_store, "GH_DATA_REPO", "someone/private-data")
    monkeypatch.setattr(json_store, "GH_DATA_TOKEN", "ghp_x")
    store = data_store("watches.json")
    assert isinstance(store, GitHubJsonStore)
    assert "someone/private-data" in store._url and store._url.endswith("watches.json")


def test_data_store_falls_back_to_local_file(monkeypatch, tmp_path):
    monkeypatch.setattr(json_store, "GH_DATA_REPO", None)
    monkeypatch.setattr(json_store, "LOCAL_DATA_DIR", tmp_path)
    store = data_store("blocks.json")
    assert isinstance(store, FileJsonStore)
    assert store.path == tmp_path / "blocks.json"


@pytest.mark.parametrize("name", ["watches.json", "blocks.json", "notify_map.json"])
def test_local_store_round_trip(monkeypatch, tmp_path, name):
    monkeypatch.setattr(json_store, "GH_DATA_REPO", None)
    monkeypatch.setattr(json_store, "LOCAL_DATA_DIR", tmp_path)
    store = data_store(name)
    assert store.load() == {}
    store.save({"a": {"x": 1}})
    assert data_store(name).load() == {"a": {"x": 1}}
