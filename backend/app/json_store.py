"""$0 persistence for small JSON objects of **runtime user data**.

``FileJsonStore``   -- a git-ignored local file (dev / no PAT configured).
``GitHubJsonStore`` -- the GitHub Contents API against a SEPARATE PRIVATE repo
                       (production). User data never touches the public code repo.

``data_store(name)`` picks the backend from the environment. Used for
``watches.json``, ``blocks.json`` and ``notify_map.json``.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx

from app.config import (
    GH_DATA_BRANCH,
    GH_DATA_REPO,
    GH_DATA_TOKEN,
    LOCAL_DATA_DIR,
    SOCRATA_TIMEOUT_SECONDS,
)


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
        body = json.dumps(data, indent=2, sort_keys=True) + "\n"
        content = base64.b64encode(body.encode()).decode()
        for attempt in range(3):
            payload = {
                "message": f"chore: update {self._path}",
                "content": content,
                "branch": self._branch,
            }
            if self._sha:
                payload["sha"] = self._sha
            resp = httpx.put(
                self._url, json=payload, headers=self._headers,
                timeout=SOCRATA_TIMEOUT_SECONDS,
            )
            if resp.status_code == 409 and attempt < 2:
                # someone else wrote it -- reload the sha and retry once
                time.sleep(0.5)
                self.load()
                continue
            resp.raise_for_status()
            self._sha = resp.json()["content"]["sha"]
            return


def data_store(name: str) -> FileJsonStore | GitHubJsonStore:
    """Backend for one runtime user-data file, chosen from the environment."""
    if GH_DATA_REPO and GH_DATA_TOKEN:
        return GitHubJsonStore(GH_DATA_REPO, GH_DATA_TOKEN, name, GH_DATA_BRANCH)
    return FileJsonStore(LOCAL_DATA_DIR / name)
