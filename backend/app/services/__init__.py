"""Plain Python clients over authoritative data sources.

They know nothing about MCP or the agent. They accept canonical inputs and return
typed evidence, converting every failure mode into ``EvidenceStatus.UNAVAILABLE``
(or ``UNSUPPORTED``) rather than a silent "no restriction".
"""

from app.services.events import get_nearby_events
from app.services.residential_zones import get_residential_zone_evidence
from app.services.snow_routes import get_snow_route_evidence, in_overnight_ban_period
from app.services.socrata import SocrataClient, SocrataError
from app.services.street_cleaning import get_street_cleaning_evidence
from app.services.street_closures import get_street_closure_evidence
from app.services.weather import get_weather_outlook

__all__ = [
    "SocrataClient",
    "SocrataError",
    "get_nearby_events",
    "get_residential_zone_evidence",
    "get_snow_route_evidence",
    "get_street_cleaning_evidence",
    "get_street_closure_evidence",
    "get_weather_outlook",
    "in_overnight_ban_period",
]
