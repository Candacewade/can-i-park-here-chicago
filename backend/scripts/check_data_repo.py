"""Verify the private data repo is reachable and writable BEFORE deploying.

    cd backend
    GH_DATA_REPO=you/can-i-park-here-chicago-data GH_DATA_TOKEN=github_pat_... \
      python scripts/check_data_repo.py

Writes a tiny `.probe.json`, reads it back, then deletes it. Exits non-zero on
any problem, with a message pointing at the fix. No secret values are printed.
"""

from __future__ import annotations

import base64
import os
import sys

import httpx

REPO = os.environ.get("GH_DATA_REPO")
TOKEN = os.environ.get("GH_DATA_TOKEN")
BRANCH = os.environ.get("GH_DATA_BRANCH", "main")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    if not REPO or not TOKEN:
        fail("set GH_DATA_REPO and GH_DATA_TOKEN in the environment")

    h = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"https://api.github.com/repos/{REPO}/contents/.probe.json"

    r = httpx.get(f"https://api.github.com/repos/{REPO}", headers=h, timeout=15)
    if r.status_code == 404:
        fail(f"repo {REPO!r} not found, or the token cannot see it")
    if r.status_code == 401:
        fail("token rejected (401) -- regenerate the fine-grained PAT")
    r.raise_for_status()
    if not r.json().get("private"):
        print("WARNING: the data repo is PUBLIC -- user data would be exposed")

    body = base64.b64encode(b'{"ok": true}\n').decode()
    r = httpx.put(
        base, headers=h, timeout=15,
        json={"message": "probe", "content": body, "branch": BRANCH},
    )
    if r.status_code == 403:
        fail("token lacks Contents: write on this repo (403)")
    if r.status_code in (404, 422):
        fail(f"write failed ({r.status_code}) -- does the '{BRANCH}' branch exist? "
             f"Add a README to the repo so the branch is created. {r.text[:150]}")
    r.raise_for_status()
    sha = r.json()["content"]["sha"]

    r = httpx.get(base, headers=h, params={"ref": BRANCH}, timeout=15)
    r.raise_for_status()
    read_back = base64.b64decode(r.json()["content"]).decode().strip()
    ok_read = read_back == '{"ok": true}'

    httpx.request(
        "DELETE", base, headers=h, timeout=15,
        json={"message": "probe cleanup", "sha": sha, "branch": BRANCH},
    )

    if not ok_read:
        fail(f"wrote but read back unexpected content: {read_back!r}")
    print(f"OK: {REPO} on '{BRANCH}' is readable and writable. Deploy away.")


if __name__ == "__main__":
    main()
