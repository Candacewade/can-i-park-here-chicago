"""Replace the network seams (Socrata, Census geocoder, NWS) with canned data so
an agent eval is reproducible while the agent's *behaviour* is still real.

``install_fixture_data`` monkeypatches at runtime (no pytest). The eval harness
calls it in-process; the MCP server subprocess calls it from ``__main__`` when
``EVAL_FIXTURES`` points at the same JSON file. ``uninstall_fixture_data`` puts
everything back (the pytest conftest calls it in teardown).

Fixture file shape::

    {
      "socrata":  { "<dataset-id>": [ {row}, ... ] | {"error": "msg"}, ... },
      "geocode":  { ...GeocodeResult fields... } | null,
      "weather":  { ...WeatherOutlookEvidence fields... } | null
    }
"""

from __future__ import annotations

import json
from pathlib import Path

_originals: dict = {}


def load(path_or_dict) -> dict:
    if isinstance(path_or_dict, dict):
        return path_or_dict
    return json.loads(Path(path_or_dict).read_text())


def install_fixture_data(path_or_dict) -> None:
    data = load(path_or_dict)
    socrata = data.get("socrata") or {}
    geocode = data.get("geocode")
    weather = data.get("weather")

    from app.locations import geocode as geo_mod
    from app.locations.geocode import GeocodeResult
    from app.mcp import handlers as handlers_mod
    from app.models.evidence import WeatherOutlookEvidence
    from app.services import socrata as socrata_mod
    from app.services import weather as weather_mod
    from app.services.socrata import SocrataError

    _originals.setdefault("SocrataClient.get_rows", socrata_mod.SocrataClient.get_rows)
    _originals.setdefault("census_geocode", geo_mod.census_geocode)
    _originals.setdefault("get_weather_outlook", weather_mod.get_weather_outlook)
    _originals.setdefault("_weather_svc", handlers_mod._weather_svc)

    def _get_rows(self, dataset_id: str, params: dict) -> list[dict]:
        canned = socrata.get(dataset_id, [])
        if isinstance(canned, dict) and "error" in canned:
            raise SocrataError(canned["error"])
        return list(canned)

    socrata_mod.SocrataClient.get_rows = _get_rows          # type: ignore[assignment]
    socrata_mod._cache.clear()

    if geocode is not None:
        geo_mod.census_geocode = lambda *a, **k: GeocodeResult(**geocode)  # type: ignore[assignment]

    if weather is not None:
        def _weather(*_a, **_k):
            return WeatherOutlookEvidence(**weather)

        weather_mod.get_weather_outlook = _weather          # type: ignore[assignment]
        handlers_mod._weather_svc = _weather                # type: ignore[assignment]


def uninstall_fixture_data() -> None:
    if not _originals:
        return
    from app.locations import geocode as geo_mod
    from app.mcp import handlers as handlers_mod
    from app.services import socrata as socrata_mod
    from app.services import weather as weather_mod

    socrata_mod.SocrataClient.get_rows = _originals["SocrataClient.get_rows"]
    geo_mod.census_geocode = _originals["census_geocode"]
    weather_mod.get_weather_outlook = _originals["get_weather_outlook"]
    handlers_mod._weather_svc = _originals["_weather_svc"]
    socrata_mod._cache.clear()
    _originals.clear()
