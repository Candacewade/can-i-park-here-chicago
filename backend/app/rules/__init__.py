"""The deterministic parking layer.

Nothing here calls an LLM. This package is the *only* place a
LEGAL / NOT_LEGAL / LEGAL_UNTIL / UNKNOWN verdict is produced.

- ``gather_evidence``   -- independently pull all evidence for a request
- ``check_completeness`` -- did we verify every safety-required category?
- ``evaluate_parking``  -- turn request + evidence into a ParkingDecision
"""

from app.rules.completeness import CompletenessResult, check_completeness, required_categories
from app.rules.engine import evaluate_parking
from app.rules.gather import gather_evidence

__all__ = [
    "CompletenessResult",
    "check_completeness",
    "evaluate_parking",
    "gather_evidence",
    "required_categories",
]
