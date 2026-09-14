"""Regression guard for the GitHub Actions cron config.

Not a YAML parse -- PyYAML isn't a project dependency and this only needs to
catch one specific regression: re-introducing an hourly cron on the exact hour.
GitHub's own docs call the top of the hour the highest-load, most
delay-prone slot for `schedule` events (see docs/monitoring.md for what was
actually observed on this repo: multi-hour delivery delays). Every hourly
`cron:` entry in the workflows dir should therefore be offset from `:00`.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parents[2].parent / ".github" / "workflows"

_HOURLY_CRON = re.compile(r'cron:\s*"(\d+)\s+\*\s+\*\s+\*\s+\*"')


def _hourly_cron_minutes(text: str) -> list[int]:
    return [int(m.group(1)) for m in _HOURLY_CRON.finditer(text)]


def test_workflows_dir_exists():
    assert WORKFLOWS_DIR.is_dir(), WORKFLOWS_DIR


def test_no_hourly_cron_fires_on_the_hour():
    yml_files = sorted(WORKFLOWS_DIR.glob("*.yml"))
    assert yml_files, "expected at least one workflow file"

    offenders = []
    for path in yml_files:
        for minute in _hourly_cron_minutes(path.read_text()):
            if minute == 0:
                offenders.append(path.name)

    assert not offenders, (
        f"hourly cron(s) scheduled exactly on the hour in {offenders}: "
        "GitHub's schedule delivery is most delay-prone at :00 -- offset the minute"
    )
