"""Run our parking assistant over a canonical ParkingRequest.

    ParkingRequest
      -> DETERMINISTIC CORE  (rules.gather + rules.engine)  -> ParkingDecision
      -> Claude Agent SDK   given the decision + core evidence as context;
                            optionally investigates (weather, events, closure
                            detail, nearby alternatives) via the MCP server
      -> deterministic re-evaluation merging any evidence the agent added
      -> agent's grounded explanation

The agent never decides legality or whether an urgent alert fires. We capture
every tool call for the trace and surface the final deterministic decision.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from app.agent.instructions import SYSTEM_PROMPT_V2
from app.config import AGENT_MODEL, BACKEND_ROOT, resolve_claude_cli
from app.mcp import handlers
from app.models.requests import ParkingRequest

MCP_SERVER_NAME = "chicago-parking"
_TOOL_PREFIX = f"mcp__{MCP_SERVER_NAME}__"


class AgentAuthError(RuntimeError):
    """The Claude Code CLI (subscription auth) could not be located.

    Only raised when the agent is explicitly required (``require_agent=True``).
    The default path degrades to a deterministic-only result instead.
    """


@dataclass
class ToolCallTrace:
    order: int
    name: str
    arguments: dict[str, Any]
    result: Any = None
    is_error: bool = False
    latency_ms: float | None = None

    def short_name(self) -> str:
        return self.name.removeprefix(_TOOL_PREFIX)


@dataclass
class AgentRunResult:
    request: ParkingRequest
    final_text: str
    run_id: str = ""
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    core_decision: dict[str, Any] | None = None   # deterministic, pre-agent
    decision: dict[str, Any] | None = None        # deterministic, post-agent (authoritative)
    agent_available: bool = True                  # False -> deterministic-only run
    duration_ms: float | None = None
    num_turns: int | None = None
    model: str = AGENT_MODEL

    @property
    def decision_status(self) -> str | None:
        payload = self.decision or self.core_decision
        if isinstance(payload, dict):
            inner = payload.get("decision", payload)
            if isinstance(inner, dict):
                return inner.get("status")
        return None


async def _only_parking_tools(
    tool_name: str, _input: dict[str, Any], _ctx: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """The agent may call our MCP toolbox and nothing else."""
    if tool_name.startswith(_TOOL_PREFIX):
        return PermissionResultAllow()
    return PermissionResultDeny(message=f"{tool_name} is not in the parking toolbox")


def _build_options() -> ClaudeAgentOptions:
    cli = resolve_claude_cli()
    if not cli:
        raise AgentAuthError(
            "Could not find the Claude Code CLI. Install it and ensure `claude` is on "
            "PATH, or set CLAUDE_CODE_CLI_PATH. The Agent SDK uses it for "
            "subscription-backed auth (we do not use ANTHROPIC_API_KEY)."
        )
    return ClaudeAgentOptions(
        model=AGENT_MODEL,
        cli_path=cli,
        system_prompt=SYSTEM_PROMPT_V2,
        setting_sources=[],  # do not inherit this repo's CLAUDE.md / settings
        cwd=str(BACKEND_ROOT),
        mcp_servers={
            MCP_SERVER_NAME: {
                "type": "stdio",
                "command": sys.executable,
                "args": ["-m", "app.mcp.server"],
                "env": {"PYTHONPATH": str(BACKEND_ROOT)},
            }
        },
        # No allowed_tools entries: every tool call falls through to can_use_tool,
        # which allows ONLY our parking toolbox. disallowed_tools is belt-and-braces.
        disallowed_tools=[
            "Bash", "Edit", "Write", "Read", "Glob", "Grep", "WebFetch", "WebSearch",
            "Task", "ToolSearch", "NotebookEdit", "TodoWrite",
        ],
        can_use_tool=_only_parking_tools,
        max_turns=12,
        permission_mode="default",
    )


def _prompt_for(request: ParkingRequest, run_id: str, core: dict) -> str:
    decision = core.get("decision", {})
    completeness = core.get("completeness", {})
    reasons = "\n".join(
        f"  - [{r.get('verdict')}] {r.get('category')}: {r.get('detail')}"
        for r in decision.get("reasons", [])
    ) or "  (none)"
    unknown = "\n".join(f"  ? {u}" for u in decision.get("unknown_reasons", [])) or "  (none)"
    return (
        "Assess this Chicago parking request. The deterministic engine has "
        "already produced the official decision below.\n\n"
        f"run_id: {run_id}\n"
        f"location_id: {request.location_id}\n"
        f"start_time: {request.start_time.isoformat()}\n"
        f"end_time: {request.end_time.isoformat()}\n"
        f"permit_zone: {request.permit_zone or 'none'}\n\n"
        "OFFICIAL DECISION (deterministic — do not change):\n"
        f"  status: {decision.get('status')}\n"
        f"  start_time_display: {decision.get('start_time_display')}\n"
        f"  end_time_display: {decision.get('end_time_display')}\n"
        f"  move_by_display: {decision.get('move_by_display')}\n"
        f"  urgent_alert: {decision.get('urgent_alert')}"
        f"  ({decision.get('urgent_reason') or 'n/a'})\n"
        f"  completeness_complete: {completeness.get('complete')}\n"
        f"  reasons:\n{reasons}\n"
        f"  unknown_reasons:\n{unknown}\n\n"
        "Investigate anything conditional this does not cover (weather/snow, "
        "nearby events, an unusual closure, alternatives), then explain the "
        "result. If you gather new evidence, call evaluate_parking_request with "
        "the run_id and explain the updated decision."
    )


def _coerce_result(content: Any) -> Any:
    """Tool results arrive as a list of content blocks; pull out JSON where we can."""
    if isinstance(content, list):
        texts = []
        for block in content:
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
            if text is not None:
                texts.append(text)
        joined = "\n".join(texts) if texts else content
    else:
        joined = content
    if isinstance(joined, str):
        try:
            return json.loads(joined)
        except (ValueError, TypeError):
            return joined
    return joined


def _core_decision(request: ParkingRequest, run_id: str) -> dict:
    """Deterministic core: gather + evaluate, with no evidence in the store yet."""
    return handlers.evaluate_parking_request(
        run_id,
        request.location_id,
        request.start_time.isoformat(),
        request.end_time.isoformat(),
        request.permit_zone,
    )


_VERDICT_LINE = {
    "LEGAL": "You can park here for the time you asked about.",
    "LEGAL_UNTIL": "You can park here now, but you must move your car by {move_by}.",
    "NOT_LEGAL": "You cannot legally park here for the time you asked about.",
    "UNKNOWN": "We could not verify whether you can park here.",
}
_MARK = {"blocks": "✗", "limits": "→", "allows": "✓"}


def _deterministic_explanation(payload: dict) -> str:
    """A plain explanation built from the rule engine alone, when the AI
    investigation/communication layer is unavailable."""
    d = (payload or {}).get("decision", {}) or {}
    status = d.get("status", "UNKNOWN")
    lines = [_VERDICT_LINE.get(status, "").format(move_by=d.get("move_by_display") or "")]
    if d.get("start_time_display") and d.get("end_time_display"):
        lines.append(f"Requested: {d['start_time_display']} through {d['end_time_display']}.")
    if d.get("urgent_alert") and d.get("urgent_reason"):
        lines.append(f"Time-sensitive: {d['urgent_reason']}")
    lines.append("")
    for r in d.get("reasons", []):
        mark = _MARK.get(r.get("verdict"), "-")
        lines.append(f"  {mark} {str(r.get('category', '')).replace('_', ' ')}: {r.get('detail')}")
    for u in d.get("unknown_reasons", []):
        lines.append(f"  ? {u}")
    lines.append("")
    lines.append(
        "This result comes from the deterministic rule engine over City of "
        "Chicago data. The AI investigation layer (snow/weather context, nearby "
        "alternatives, richer wording) is currently unavailable."
    )
    return "\n".join(line for line in lines if line is not None).strip()


async def run_parking_agent(
    request: ParkingRequest, *, require_agent: bool = False
) -> AgentRunResult:
    run_id = uuid.uuid4().hex
    result = AgentRunResult(request=request, final_text="", run_id=run_id)

    # 1. Deterministic core runs first, unconditionally -- this is the answer.
    result.core_decision = _core_decision(request, run_id)
    result.decision = result.core_decision

    # 2. The agent is optional enrichment. No runtime -> deterministic explanation.
    if resolve_claude_cli() is None:
        if require_agent:
            raise AgentAuthError(
                "The Claude Code CLI (subscription auth) was not found. We do not "
                "use ANTHROPIC_API_KEY."
            )
        result.agent_available = False
        result.model = "deterministic"
        result.final_text = _deterministic_explanation(result.core_decision)
        return result

    options = _build_options()
    pending: dict[str, ToolCallTrace] = {}
    started_at: dict[str, float] = {}
    order = 0

    prompt = _prompt_for(request, run_id, result.core_decision)
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    order += 1
                    trace = ToolCallTrace(
                        order=order, name=block.name, arguments=dict(block.input or {})
                    )
                    pending[block.id] = trace
                    started_at[block.id] = time.monotonic()
                    result.tool_calls.append(trace)
                elif isinstance(block, TextBlock):
                    result.final_text = block.text
                elif isinstance(block, ThinkingBlock):
                    pass
        elif isinstance(message, UserMessage):
            content = message.content if isinstance(message.content, list) else []
            for block in content:
                if isinstance(block, ToolResultBlock):
                    trace = pending.pop(block.tool_use_id, None)
                    if trace is None:
                        continue
                    t0 = started_at.pop(block.tool_use_id, None)
                    if t0 is not None:
                        trace.latency_ms = round((time.monotonic() - t0) * 1000, 1)
                    trace.is_error = bool(block.is_error)
                    trace.result = _coerce_result(block.content)
                    _record_evidence(result, trace)
        elif isinstance(message, ResultMessage):
            result.duration_ms = float(message.duration_ms) if message.duration_ms else None
            result.num_turns = message.num_turns
            if getattr(message, "result", None):
                result.final_text = message.result

    # Authoritative final decision: re-run deterministically, merging whatever
    # optional evidence the agent's tools stored for this run. Independent of
    # whether the agent itself called evaluate_parking_request.
    result.decision = _core_decision(request, run_id)
    return result


_INVESTIGATION_KEYS = {
    "get_weather_outlook": "weather",
    "get_snow_route_status": "snow_route",
    "get_nearby_events": "events",
    "get_closure_detail": "closure_detail",
    "find_legal_parking_nearby": "nearby",
}


def _record_evidence(result: AgentRunResult, trace: ToolCallTrace) -> None:
    """Keep the last result of each investigation tool for the trace view."""
    name = trace.short_name()
    if name in _INVESTIGATION_KEYS:
        result.evidence[_INVESTIGATION_KEYS[name]] = trace.result
    elif name == "get_location_context":
        result.evidence["location_context"] = trace.result


def format_trace(result: AgentRunResult) -> str:
    """A compact, human-readable trace of the run (Master Build Plan sec. 29 / 42)."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("PARKING AGENT RUN")
    lines.append("=" * 60)
    lines.append(f"location_id : {result.request.location_id}")
    lines.append(
        f"interval    : {result.request.start_time.isoformat()} -> "
        f"{result.request.end_time.isoformat()}"
    )
    lines.append(f"permit_zone : {result.request.permit_zone or 'none'}")
    lines.append(f"model       : {result.model}")
    lines.append("-" * 60)
    for call in result.tool_calls:
        status = "ERROR" if call.is_error else "ok"
        lat = f"{call.latency_ms:.0f}ms" if call.latency_ms is not None else "-"
        lines.append(f"[{call.order}] {call.short_name()}  ({status}, {lat})")
        lines.append(f"      args: {json.dumps(call.arguments)}")
        preview = json.dumps(call.result)[:300] if call.result is not None else "None"
        lines.append(f"      -> {preview}")
    lines.append("-" * 60)
    lines.append(f"tool calls  : {len(result.tool_calls)}")
    if result.duration_ms:
        lines.append(f"duration    : {result.duration_ms / 1000:.1f}s")
    lines.append("-" * 60)
    payload = result.decision or result.core_decision or {}
    inner = payload.get("decision", {})
    comp = payload.get("completeness", {})
    core_status = (result.core_decision or {}).get("decision", {}).get("status")
    lines.append("DETERMINISTIC DECISION")
    lines.append(f"  status     : {inner.get('status')}"
                 + (f"   (core: {core_status})" if core_status != inner.get("status") else ""))
    lines.append(
        f"  interval   : {inner.get('start_time_display')} -> {inner.get('end_time_display')}"
    )
    if inner.get("move_by_display"):
        lines.append(f"  move_by    : {inner['move_by_display']}")
    if inner.get("urgent_alert"):
        lines.append(f"  URGENT     : {inner.get('urgent_reason')}")
    for reason in inner.get("reasons", []):
        lines.append(
            f"  - [{reason.get('verdict')}] {reason.get('category')}: {reason.get('detail')}"
        )
    for ur in inner.get("unknown_reasons", []):
        lines.append(f"  ? {ur}")
    lines.append(f"  complete   : {comp.get('complete')}")
    lines.append("-" * 60)
    lines.append(
        "EXPLANATION (agent)" if result.agent_available
        else "EXPLANATION (deterministic — agent runtime unavailable)"
    )
    lines.append(result.final_text.strip() or "(no text)")
    lines.append("=" * 60)
    return "\n".join(lines)
