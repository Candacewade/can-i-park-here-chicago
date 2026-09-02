"""Persistence for watches -- $0, no database.

Two backends, chosen by environment:

- ``FileWatchStore``   reads/writes a local ``watches.json`` (the scheduled
  GitHub Actions job uses this on a real checkout and commits the file back).
- ``GitHubWatchStore`` reads/writes ``watches.json`` through the GitHub contents
  API (for the API when it runs somewhere without a durable filesystem, e.g.
  Render).

Either way the file contains anonymous ids + state only -- never an email.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from app.config import (
    GH_WATCHES_BRANCH,
    GH_WATCHES_PATH,
    GH_WATCHES_REPO,
    GH_WATCHES_TOKEN,
    SOCRATA_TIMEOUT_SECONDS,
    WATCHES_FILE,
)
from app.monitor.models import Watch


def _decode(raw: str) -> dict[str, Watch]:
    data = json.loads(raw or "{}")
    return {wid: Watch.model_validate(w) for wid, w in data.items()}


def _encode(watches: dict[str, Watch]) -> str:
    return json.dumps(
        {wid: json.loads(w.model_dump_json()) for wid, w in sorted(watches.items())},
        indent=2,
    ) + "\n"


class FileWatchStore:
    def __init__(self, path: Path = WATCHES_FILE) -> None:
        self.path = path

    def load(self) -> dict[str, Watch]:
        if not self.path.exists():
            return {}
        return _decode(self.path.read_text())

    def save(self, watches: dict[str, Watch]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(_encode(watches))


class GitHubWatchStore:
    def __init__(self, repo: str, token: str, path: str, branch: str) -> None:
        self._url = f"https://api.github.com/repos/{repo}/contents/{path}"
        self._branch = branch
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._sha: str | None = None

    def load(self) -> dict[str, Watch]:
        resp = httpx.get(
            self._url, params={"ref": self._branch},
            headers=self._headers, timeout=SOCRATA_TIMEOUT_SECONDS,
        )
        if resp.status_code == 404:
            self._sha = None
            return {}
        resp.raise_for_status()
        body = resp.json()
        self._sha = body["sha"]
        return _decode(base64.b64decode(body["content"]).decode())

    def save(self, watches: dict[str, Watch]) -> None:
        payload = {
            "message": "chore: update watch state",
            "content": base64.b64encode(_encode(watches).encode()).decode(),
            "branch": self._branch,
        }
        if self._sha:
            payload["sha"] = self._sha
        resp = httpx.put(
            self._url, json=payload, headers=self._headers, timeout=SOCRATA_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        self._sha = resp.json()["content"]["sha"]


def get_store() -> FileWatchStore | GitHubWatchStore:
    if GH_WATCHES_REPO and GH_WATCHES_TOKEN:
        return GitHubWatchStore(
            GH_WATCHES_REPO, GH_WATCHES_TOKEN, GH_WATCHES_PATH, GH_WATCHES_BRANCH
        )
    return FileWatchStore()
