"""Plain Python clients over authoritative City of Chicago datasets.

These know nothing about MCP or the agent. They accept canonical inputs
(a ChicagoParkingLocation + interval) and return typed evidence, converting
every failure mode into ``EvidenceStatus.UNAVAILABLE`` rather than a silent
"no restriction".
"""

from app.services.residential_zones import get_residential_zone_evidence
from app.services.socrata import SocrataClient, SocrataError
from app.services.street_cleaning import get_street_cleaning_evidence

__all__ = [
    "SocrataClient",
    "SocrataError",
    "get_residential_zone_evidence",
    "get_street_cleaning_evidence",
]
