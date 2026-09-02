"""The monitor pass.

Two shapes, one code path:

* **full**  (daily cron) -- every active watch: deterministic core -> which
  messages are due -> if something is due AND the agent runtime is available,
  have the agent investigate + write the prose -> send + record state.

* **urgent_only**  (hourly cron) -- deterministic core only. Does nothing unless
  the engine reports a *new* urgent condition (a cause hash not already in the
  watch's ``notified``). Only then does communication run, and only then may the
  agent run -- for that one watch. Never churns ``watches.json`` on a quiet poll.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.agent.parking_agent import run_parking_agent
from app.config import CHICAGO_TZ, resolve_claude_cli
from app.models.decision import ParkingDecision
from app.models.requests import ParkingRequest
from app.monitor import notify
from app.monitor.compose import compose_email
from app.monitor.models import Watch, WatchStatus
from app.monitor.schedule import MessageType, due_messages, notified_key, primary
from app.monitor.store import FileWatchStore, GitHubWatchStore, get_store
from app.rules.engine import evaluate_parking
from app.rules.gather import gather_evidence
from app.services.email import send_email


@dataclass
class WatchOutcome:
    watch_id: str
    status: str
    messages: list[str] = field(default_factory=list)
    sent_to_email: bool = False
    delivery: str | None = None
    note: str | None = None


@dataclass
class MonitorReport:
    ran_at: datetime
    mode: str = "full"
    agent_used: bool = False
    checked: int = 0
    emails_sent: int = 0
    outcomes: list[WatchOutcome] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Monitor run ({self.mode}, agent={'on' if self.agent_used else 'off'}) "
            f"{self.ran_at.isoformat()} - {self.checked} checked, {self.emails_sent} emails"
        ]
        for o in self.outcomes:
            tail = f" -> {o.delivery}" if o.delivery else ""
            note = f"  ({o.note})" if o.note else ""
            lines.append(
                f"  {o.watch_id}: {o.status}  {','.join(o.messages) or '-'}{tail}{note}"
            )
        return "\n".join(lines)


def _request(watch: Watch) -> ParkingRequest:
    return ParkingRequest(
        location_id=watch.location_id,
        start_time=watch.start_time,
        end_time=watch.end_time,
        permit_zone=watch.permit_zone,
    )


async def _investigate(request: ParkingRequest, decision: ParkingDecision):
    """Run the agent for one watch; returns (decision, prose) or (decision, None)
    if the runtime is unavailable/failed."""
    try:
        result = await run_parking_agent(request)
    except Exception as exc:  # any agent failure -> deterministic fallback for this watch
        print(f"  agent unavailable for {request.location_id}: {exc}")
        return decision, None
    if result.decision:
        decision = ParkingDecision.model_validate(result.decision["decision"])
    return decision, (result.final_text or None)


async def run_monitor(
    now: datetime | None = None,
    store: FileWatchStore | GitHubWatchStore | None = None,
    use_agent: bool = True,
    urgent_only: bool = False,
) -> MonitorReport:
    now = now or datetime.now(tz=CHICAGO_TZ)
    store = store or get_store()
    watches = store.load()

    agent_available = use_agent and resolve_claude_cli() is not None
    report = MonitorReport(
        ran_at=now, mode="urgent_only" if urgent_only else "full", agent_used=agent_available
    )
    changed = False

    for watch in watches.values():
        if watch.status != WatchStatus.ACTIVE:
            continue
        if now >= watch.end_time:
            if not urgent_only:
                watch.status = WatchStatus.EXPIRED
                changed = True
                report.outcomes.append(WatchOutcome(watch.watch_id, "expired"))
            continue

        report.checked += 1
        request = _request(watch)

        evidence = gather_evidence(request)
        decision = evaluate_parking(request, evidence)
        due = due_messages(watch, decision, now)
        if urgent_only:
            due = [m for m in due if m is MessageType.URGENT]

        prose: str | None = None
        if due and agent_available:
            decision, prose = await _investigate(request, decision)
            due = due_messages(watch, decision, now)
            if urgent_only:
                due = [m for m in due if m is MessageType.URGENT]

        # A quiet urgent poll leaves the watch (and watches.json) untouched.
        if urgent_only and not due:
            report.outcomes.append(WatchOutcome(watch.watch_id, decision.status.value))
            continue

        if not urgent_only:
            watch.last_decision = decision.status.value
            watch.last_checked_at = now
            changed = True

        outcome = WatchOutcome(watch.watch_id, decision.status.value)
        msg = primary(due)
        if msg is not None:
            outcome.messages = [m.name for m in due]
            email = compose_email(watch, decision, msg, prose)
            dest = notify.get_email(watch.watch_id)
            if dest:
                outcome.delivery = send_email(dest, email.subject, email.body_text)
                outcome.sent_to_email = True
                report.emails_sent += 1
                for m in due:
                    watch.notified.append(notified_key(m, decision, now))
                changed = True
            else:
                outcome.note = "no notification destination registered; not sent"
        report.outcomes.append(outcome)

    if changed:
        store.save(watches)
    return report
