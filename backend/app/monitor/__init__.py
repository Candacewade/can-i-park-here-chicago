"""Proactive monitoring (Master Build Plan sec. 0 / docs/monitoring.md).

A registered *watch* on a parked car. A daily scheduled run re-evaluates it with
the deterministic core, and -- when a message is due -- has the agent compose a
morning summary, an urgent alert (deterministically triggered), or a move
reminder (T-N days / the night before).

No PII is stored in the repo: watches.json holds anonymous ids + state; the
watch_id -> email map lives in a secret.
"""

from app.monitor.models import Watch, WatchStatus
from app.monitor.run import MonitorReport, run_monitor

__all__ = ["MonitorReport", "Watch", "WatchStatus", "run_monitor"]
