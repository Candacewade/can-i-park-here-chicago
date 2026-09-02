"""Generic $0 persistence for a small JSON object.

``FileJsonStore``   -- a local file (dev, and the scheduled GitHub Actions job on
                       a real checkout, which commits the file back).
``GitHubJsonStore`` -- the GitHub contents API (for a service without a durable
                       filesystem, e.g. Render).

Used for ``watches.json`` state and the ``blocks.json`` location cache. No
database.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from app.config import SOCRATA_TIMEOUT_SECONDS


class FileJsonStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text() or "{}")
        except (ValueError, OSError):
            return {}

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


class GitHubJsonStore:
    def __init__(self, repo: str, token: str, path: str, branch: str) -> None:
        self._url = f"https://api.github.com/repos/{repo}/contents/{path}"
        self._branch = branch
        self._path = path
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._sha: str | None = None

    def load(self) -> dict:
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
        return json.loads(base64.b64decode(body["content"]).decode() or "{}")

    def save(self, data: dict) -> None:
        payload = {
            "message": f"chore: update {self._path}",
            "content": base64.b64encode(
                (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
            ).decode(),
            "branch": self._branch,
        }
        if self._sha:
            payload["sha"] = self._sha
        resp = httpx.put(
            self._url, json=payload, headers=self._headers, timeout=SOCRATA_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        self._sha = resp.json()["content"]["sha"]
