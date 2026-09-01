"""Run our parking agent over a canonical ParkingRequest.

    ParkingRequest
      -> Claude Agent SDK  (agent chooses which evidence tools to call)
      -> our stdio MCP server -> real Chicago data
      -> evaluate_parking_request  (deterministic: re-gather + completeness + verdict)
      -> agent explains the ParkingDecision

The agent decides *which* MCP tools to call and with what arguments. We capture
every tool call (name, args, result, latency, order) so the run is fully
observable, and we surface the deterministic decision the evaluator returned.
"""

from __future__ import annotations

import json
import sys
import time
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

from app.agent.instructions import SYSTEM_PROMPT_V1
from app.config import AGENT_MODEL, BACKEND_ROOT, resolve_claude_cli
from app.models.requests import ParkingRequest

MCP_SERVER_NAME = "chicago-parking"
_TOOL_PREFIX = f"mcp__{MCP_SERVER_NAME}__"


class AgentAuthError(RuntimeError):
    """The Claude Code CLI (subscription auth) could not be located."""


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
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] | None = None  # from evaluate_parking_request, if the agent called it
    duration_ms: float | None = None
    num_turns: int | None = None
    model: str = AGENT_MODEL

    @property
    def decision_status(self) -> str | None:
        if isinstance(self.decision, dict):
            inner = self.decision.get("decision", self.decision)
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
        system_prompt=SYSTEM_PROMPT_V1,
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


def _prompt_for(request: ParkingRequest) -> str:
    return (
        "Assess this parking request: gather the evidence it needs, get the "
        "official decision from evaluate_parking_request, then explain it.\n\n"
        f"location_id: {request.location_id}\n"
        f"start_time: {request.start_time.isoformat()}\n"
        f"end_time: {request.end_time.isoformat()}\n"
        f"permit_zone: {request.permit_zone or 'none'}\n"
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


async def run_parking_agent(request: ParkingRequest) -> AgentRunResult:
    options = _build_options()
    result = AgentRunResult(request=request, final_text="")

    pending: dict[str, ToolCallTrace] = {}
    started_at: dict[str, float] = {}
    order = 0

    async for message in query(prompt=_prompt_for(request), options=options):
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

    return result


def _record_evidence(result: AgentRunResult, trace: ToolCallTrace) -> None:
    """Keep the last result of each tool as the collected evidence / decision."""
    name = trace.short_name()
    if name == "get_residential_restrictions":
        result.evidence["residential"] = trace.result
    elif name == "get_street_cleaning_restrictions":
        result.evidence["street_cleaning"] = trace.result
    elif name == "get_temporary_closures":
        result.evidence["temporary_closure"] = trace.result
    elif name == "get_location_context":
        result.evidence["location_context"] = trace.result
    elif name == "evaluate_parking_request" and isinstance(trace.result, dict):
        result.decision = trace.result


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
    lines.append("DETERMINISTIC DECISION (evaluate_parking_request)")
    if result.decision is None:
        lines.append("  (agent did not call the evaluator)")
    else:
        inner = result.decision.get("decision", {})
        comp = result.decision.get("completeness", {})
        lines.append(f"  status   : {inner.get('status')}")
        if inner.get("move_by"):
            lines.append(f"  move_by  : {inner['move_by']}")
        for reason in inner.get("reasons", []):
            lines.append(
                f"  - [{reason.get('verdict')}] {reason.get('category')}: {reason.get('detail')}"
            )
        for ur in inner.get("unknown_reasons", []):
            lines.append(f"  ? {ur}")
        lines.append(f"  complete : {comp.get('complete')}")
    lines.append("-" * 60)
    lines.append("AGENT EXPLANATION")
    lines.append(result.final_text.strip() or "(no text)")
    lines.append("=" * 60)
    return "\n".join(lines)
