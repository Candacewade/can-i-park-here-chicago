"""Entry point for the scheduled GitHub Actions workflows:

    python -m app.monitor                 daily pass: morning summary, reminders,
                                          urgent alerts. Uses the Claude agent
                                          when the runtime is available.
    python -m app.monitor --urgent-only   frequent (hourly) poll: deterministic
                                          only; sends an email ONLY when a NEW
                                          urgent condition appears.
    python -m app.monitor --no-agent      force deterministic templates (used by
                                          the daily workflow when no Claude
                                          runtime token is configured).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.monitor.run import run_monitor


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Chicago parking monitor.")
    parser.add_argument("--no-agent", action="store_true", help="skip the Claude agent")
    parser.add_argument(
        "--urgent-only",
        action="store_true",
        help="deterministic poll; only act on a new urgent condition",
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_monitor(use_agent=not args.no_agent, urgent_only=args.urgent_only)
    )
    print(report.summary())
    # Non-zero only on hard failure; a quiet poll is success.
    sys.exit(0)


if __name__ == "__main__":
    main()
