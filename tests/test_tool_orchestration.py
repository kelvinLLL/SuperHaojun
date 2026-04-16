"""Tests for dedicated tool orchestration."""

from __future__ import annotations

import json
from typing import Any

import pytest

from superhaojun.bus import MessageBus
from superhaojun.messages import ToolCallEnd, ToolCallStart
from superhaojun.permissions import PermissionChecker
from superhaojun.tool_orchestration import ToolCallInfo, ToolOrchestrator
from superhaojun.tools.base import Tool
from superhaojun.tools.registry import ToolRegistry


class _EchoTool(Tool):
    @property
    def name(self) -> str:
        return "echo_tool"

    @property
    def description(self) -> str:
        return "Echo a value"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return f"echo:{kwargs['value']}"


class _WriteTool(Tool):
    def __init__(self) -> None:
        self.executed = 0

    @property
    def name(self) -> str:
        return "write_tool"

    @property
    def description(self) -> str:
        return "Write something"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    @property
    def is_concurrent_safe(self) -> bool:
        return False

    @property
    def risk_level(self) -> str:
        return "write"

    async def execute(self, **kwargs: Any) -> str:
        self.executed += 1
        return "wrote"


def _collect_from_bus(bus: MessageBus) -> list[object]:
    collected: list[object] = []
    for msg_type in ("tool_call_start", "tool_call_end", "permission_request"):
        bus.on(msg_type, lambda m, c=collected: c.append(m))
    return collected


@pytest.mark.asyncio
async def test_execute_tool_calls_returns_results_and_emits_events() -> None:
    bus = MessageBus()
    registry = ToolRegistry()
    registry.register(_EchoTool())
    collected = _collect_from_bus(bus)

    orchestrator = ToolOrchestrator(
        bus=bus,
        registry=registry,
        permission_checker=PermissionChecker(),
    )

    results = await orchestrator.execute_tool_calls([
        ToolCallInfo(id="tc1", name="echo_tool", arguments=json.dumps({"value": "a"})),
        ToolCallInfo(id="tc2", name="echo_tool", arguments=json.dumps({"value": "b"})),
    ])

    assert [r.content for r in results] == ["echo:a", "echo:b"]
    assert len([m for m in collected if isinstance(m, ToolCallStart)]) == 2
    assert len([m for m in collected if isinstance(m, ToolCallEnd)]) == 2


@pytest.mark.asyncio
async def test_denied_tool_returns_permission_error_without_execution() -> None:
    bus = MessageBus()
    registry = ToolRegistry()
    tool = _WriteTool()
    registry.register(tool)
    checker = PermissionChecker()
    checker.deny_always("write_tool")

    orchestrator = ToolOrchestrator(
        bus=bus,
        registry=registry,
        permission_checker=checker,
    )

    results = await orchestrator.execute_tool_calls([
        ToolCallInfo(id="tc1", name="write_tool", arguments="{}"),
    ])

    assert len(results) == 1
    assert results[0].content == "Permission denied for tool 'write_tool'"
    assert tool.executed == 0
