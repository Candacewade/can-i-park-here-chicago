"""The daily monitor pass.

For every active watch: run the deterministic core, decide (deterministically)
which messages are due, and -- only when something is due and the agent runtime
is available -- have the agent investigate and write the prose. Then send and
record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.agent.parking_agent import AgentAuthError, run_parking_agent
from app.config import CHICAGO_TZ
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
    checked: int = 0
    emails_sent: int = 0
    outcomes: list[WatchOutcome] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Monitor run {self.ran_at.isoformat()} - "
            f"{self.checked} watches, {self.emails_sent} emails"
        ]
        for o in self.outcomes:
            tail = f" -> {o.delivery}" if o.delivery else ""
            note = f"  ({o.note})" if o.note else ""
            lines.append(f"  {o.watch_id}: {o.status}  {','.join(o.messages) or '-'}{tail}{note}")
        return "\n".join(lines)


def _request(watch: Watch) -> ParkingRequest:
    return ParkingRequest(
        location_id=watch.location_id,
        start_time=watch.start_time,
        end_time=watch.end_time,
        permit_zone=watch.permit_zone,
    )


async def run_monitor(
    now: datetime | None = None,
    store: FileWatchStore | GitHubWatchStore | None = None,
    use_agent: bool = True,
) -> MonitorReport:
    now = now or datetime.now(tz=CHICAGO_TZ)
    store = store or get_store()
    watches = store.load()
    report = MonitorReport(ran_at=now)
    changed = False

    for watch in watches.values():
        if watch.status != WatchStatus.ACTIVE:
            continue
        if now >= watch.end_time:
            watch.status = WatchStatus.EXPIRED
            changed = True
            report.outcomes.append(WatchOutcome(watch.watch_id, "expired"))
            continue

        report.checked += 1
        request = _request(watch)

        evidence = gather_evidence(request)
        decision = evaluate_parking(request, evidence)
        due = due_messages(watch, decision, now)
        prose: str | None = None

        if due and use_agent:
            try:
                agent_result = await run_parking_agent(request)
                if agent_result.decision:
                    decision = ParkingDecision.model_validate(
                        agent_result.decision["decision"]
                    )
                prose = agent_result.final_text or None
                due = due_messages(watch, decision, now)  # investigation may shift it
            except AgentAuthError:
                pass  # deterministic template only

        watch.last_decision = decision.status.value
        watch.last_checked_at = now
        changed = True

        outcome = WatchOutcome(watch.watch_id, decision.status.value)
        msg = primary(due)
        if msg is not None:
            outcome.messages = [MessageType(m).name for m in due]
            email = compose_email(watch, decision, msg, prose)
            dest = notify.get_email(watch.watch_id)
            if dest:
                delivery = send_email(dest, email.subject, email.body_text)
                outcome.sent_to_email = True
                outcome.delivery = delivery
                report.emails_sent += 1
                for m in due:
                    watch.notified.append(notified_key(m, decision, now))
            else:
                outcome.note = "no notification destination registered; not sent"
        report.outcomes.append(outcome)

    if changed:
        store.save(watches)
    return report
