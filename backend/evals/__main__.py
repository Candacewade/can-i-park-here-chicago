from __future__ import annotations

import argparse
import asyncio
import json
import sys

from evals.runner import metrics, report, run_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the agent evaluation suite.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    results = asyncio.run(run_all())

    if args.json:
        print(json.dumps({
            "metrics": metrics(results),
            "scenarios": [
                {
                    "id": r.scenario_id, "passed": r.passed, "status": r.status,
                    "expected": r.expected_status, "tools": r.tools_called,
                    "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in r.checks],
                }
                for r in results
            ],
        }, indent=2))
    else:
        print(report(results))

    sys.exit(0 if all(r.passed for r in results) else 1)


if __name__ == "__main__":
    main()
