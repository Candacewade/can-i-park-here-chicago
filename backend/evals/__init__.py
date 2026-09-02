"""Agent evaluation suite (Master Build Plan sec. 38-39, docs/evaluations.md).

Each scenario pins the City data (canned fixtures) so the run is reproducible,
then runs the REAL agent and scores its behaviour: tool selection, the
deterministic verdict it lands on, and what its explanation does/doesn't say.

Run:  python -m evals            (spends Claude subscription usage -- NOT in CI)
      python -m evals --json
"""
