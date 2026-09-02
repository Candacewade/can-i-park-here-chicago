"""Run the eval scenarios and score them."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field

from app.models.requests import ParkingRequest
from evals.scenarios import SCENARIOS, Scenario


@dataclass
class ScenarioResult:
    scenario_id: str
    status: str | None
    expected_status: str
    tools_called: list[str]
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    explanation: str = ""

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


def _contains_all(text: str, needles: list[str]) -> tuple[bool, list[str]]:
    low = text.lower()
    missing = [n for n in needles if n.lower() not in low]
    return (not missing), missing


def _contains_none(text: str, needles: list[str]) -> tuple[bool, list[str]]:
    low = text.lower()
    hit = [n for n in needles if n.lower() in low]
    return (not hit), hit


async def run_scenario(sc: Scenario) -> ScenarioResult:
    from app.locations import registry
    from app.testing.fixtures import install_fixture_data

    fx = sc.fixtures()
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", prefix=f"eval-{sc.id}-", delete=False
    ) as fh:
        json.dump(fx, fh)
        fx_path = fh.name

    os.environ["EVAL_FIXTURES"] = fx_path      # forwarded to the MCP subprocess
    install_fixture_data(fx)                    # patch this process too
    registry.reset_cache()

    try:
        from app.agent.parking_agent import run_parking_agent

        request = ParkingRequest(
            location_id=sc.location_id, start_time=sc.start, end_time=sc.end,
            permit_zone=sc.permit_zone,
        )
        result = await run_parking_agent(request, require_agent=True)
    finally:
        os.environ.pop("EVAL_FIXTURES", None)
        try:
            os.unlink(fx_path)
        except OSError:
            pass

    tools = [c.short_name() for c in result.tool_calls]
    text = result.final_text or ""
    r = ScenarioResult(
        scenario_id=sc.id, status=result.decision_status,
        expected_status=sc.expected_status, tools_called=tools, explanation=text,
    )

    r.checks.append((
        "decision status", result.decision_status == sc.expected_status,
        f"got {result.decision_status}, expected {sc.expected_status}",
    ))
    if sc.move_by_contains:
        inner = (result.decision or {}).get("decision", {})
        mbd = inner.get("move_by_display") or ""
        r.checks.append((
            f"move_by contains {sc.move_by_contains!r}", sc.move_by_contains in mbd,
            f"move_by_display={mbd!r}",
        ))
    if sc.required_tools:
        missing = sc.required_tools - set(tools)
        r.checks.append((
            f"required tools {sorted(sc.required_tools)}", not missing,
            f"missing {sorted(missing)}" if missing else "all present",
        ))
    if sc.forbidden_tools:
        used = sc.forbidden_tools & set(tools)
        r.checks.append((
            f"forbidden tools {sorted(sc.forbidden_tools)}", not used,
            f"used {sorted(used)}" if used else "none used",
        ))
    if sc.must_say:
        ok, missing = _contains_all(text, sc.must_say)
        r.checks.append((f"explanation says {sc.must_say}", ok, f"missing {missing}"))
    ok, hit = _contains_none(text, sc.must_not_say)
    r.checks.append(("no loose reassurance", ok, f"found {hit}" if hit else "clean"))

    return r


async def run_all() -> list[ScenarioResult]:
    results = []
    for sc in SCENARIOS:
        print(f"  running {sc.id} ...", flush=True)
        results.append(await run_scenario(sc))
    return results


def metrics(results: list[ScenarioResult]) -> dict:
    n = len(results)
    return {
        "scenarios": n,
        "passed": sum(r.passed for r in results),
        "decision_accuracy": round(
            sum(r.status == r.expected_status for r in results) / n, 3
        ),
        "avg_tool_calls": round(sum(len(r.tools_called) for r in results) / n, 2),
        "reassurance_violations": sum(
            1 for r in results
            for name, ok, _ in r.checks if name == "no loose reassurance" and not ok
        ),
    }


def report(results: list[ScenarioResult]) -> str:
    lines = ["", "=" * 70, "AGENT EVALUATION", "=" * 70]
    for r in results:
        flag = "PASS" if r.passed else "FAIL"
        lines.append(f"\n[{flag}] {r.scenario_id}   status={r.status}  tools={r.tools_called}")
        for name, ok, detail in r.checks:
            lines.append(f"    {'ok ' if ok else 'XX '} {name}  ({detail})")
        if not r.passed:
            lines.append(f"    --- explanation ---\n{_indent(r.explanation)}")
    m = metrics(results)
    lines += ["", "-" * 70]
    lines += [f"{k:22s}: {v}" for k, v in m.items()]
    lines.append("=" * 70)
    return "\n".join(lines)


def _indent(text: str) -> str:
    return "\n".join("        " + ln for ln in text.strip().splitlines())
