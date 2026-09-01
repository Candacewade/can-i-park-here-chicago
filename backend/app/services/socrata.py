"""Thin wrapper over the Socrata Open Data API (SODA).

One job: turn "I want rows from dataset X matching filter Y" into a list of dicts,
and turn *every* failure -- network, timeout, HTTP error, non-JSON body, wrong
shape -- into a single ``SocrataError``. Callers above translate that into
``EvidenceStatus.UNAVAILABLE``.
"""

from __future__ import annotations

import httpx

from app.config import SOCRATA_APP_TOKEN, SOCRATA_DOMAIN, SOCRATA_TIMEOUT_SECONDS


class SocrataError(RuntimeError):
    """Any failure retrieving or parsing authoritative data from the City portal."""


class SocrataClient:
    def __init__(
        self,
        domain: str = SOCRATA_DOMAIN,
        app_token: str | None = SOCRATA_APP_TOKEN,
        timeout: float = SOCRATA_TIMEOUT_SECONDS,
    ) -> None:
        self._base = f"https://{domain}/resource"
        self._timeout = timeout
        self._headers = {"Accept": "application/json"}
        if app_token:
            self._headers["X-App-Token"] = app_token

    def get_rows(self, dataset_id: str, params: dict[str, str]) -> list[dict]:
        """Run a SODA query. ``params`` uses SODA keys like ``$where``, ``$limit``."""
        url = f"{self._base}/{dataset_id}.json"
        try:
            resp = httpx.get(
                url, params=params, headers=self._headers, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise SocrataError(f"timeout querying {dataset_id}") from exc
        except httpx.HTTPError as exc:
            raise SocrataError(f"network error querying {dataset_id}: {exc}") from exc

        if resp.status_code == 429:
            raise SocrataError(f"rate limited (429) by City portal on {dataset_id}")
        if resp.status_code >= 400:
            raise SocrataError(
                f"City portal returned HTTP {resp.status_code} for {dataset_id}"
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise SocrataError(f"non-JSON response from {dataset_id}") from exc

        if not isinstance(body, list):
            raise SocrataError(
                f"unexpected response shape from {dataset_id}: {type(body).__name__}"
            )
        return body

    def query_url(self, dataset_id: str, params: dict[str, str]) -> str:
        """The URL a query resolves to -- recorded in evidence provenance for tracing."""
        q = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self._base}/{dataset_id}.json?{q}"
