"""Entry point for the scheduled GitHub Actions workflow:

    python -m app.monitor          run the daily pass, print the report
    python -m app.monitor --no-agent   deterministic templates only (CI without Claude)
"""

from __future__ import annotations

import argparse
import asyncio

from app.monitor.run import run_monitor


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Chicago parking monitor.")
    parser.add_argument("--no-agent", action="store_true", help="skip the Claude agent")
    args = parser.parse_args()

    report = asyncio.run(run_monitor(use_agent=not args.no_agent))
    print(report.summary())


if __name__ == "__main__":
    main()
