"""The deterministic parking layer.

Nothing here calls an LLM. This package is the *only* place a
LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN verdict, a move-by time, or a hard
urgent-alert trigger is produced.

- ``gather_evidence``    -- the required core gather, runs on every request
- ``check_completeness`` -- did we verify every safety-required category?
- ``evaluate_parking``   -- request + evidence -> ParkingDecision
- ``find_legal_parking_nearby`` -- deterministic alternative-parking search
"""

from app.rules.completeness import CompletenessResult, check_completeness, required_categories
from app.rules.engine import evaluate_parking
from app.rules.gather import gather_evidence
from app.rules.nearby import NearbyOption, find_legal_parking_nearby

__all__ = [
    "CompletenessResult",
    "NearbyOption",
    "check_completeness",
    "evaluate_parking",
    "find_legal_parking_nearby",
    "gather_evidence",
    "required_categories",
]
