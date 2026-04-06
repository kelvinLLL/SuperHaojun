"""Tests for permission system."""

from __future__ import annotations

import asyncio
import json

import pytest

from superhaojun.agent import Agent, ToolCallInfo
from superhaojun.bus import MessageBus
from superhaojun.config import ModelConfig
from superhaojun.messages import (
    PermissionRequest, PermissionResponse,
    ToolCallStart, ToolCallEnd,
)
from superhaojun.permissions import Decision, PermissionChecker, PermissionRule
from superhaojun.tools import ReadFileTool, ToolRegistry
from superhaojun.tools.bash import BashTool


@pytest.fixture
def config() -> ModelConfig:
    return ModelConfig(
        provider="openai", model_id="gpt-4o",
        base_url="https://api.openai.com/v1", api_key="sk-test",
    )


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus()


class TestPermissionRule:
    def test_frozen(self) -> None:
        rule = PermissionRule(tool_name="bash", decision=Decision.DENY)
        with pytest.raises(AttributeError):
            rule.decision = Decision.ALLOW  # type: ignore[misc]

    def test_default_decision(self) -> None:
        rule = PermissionRule()
        assert rule.decision == Decision.ASK


class TestPermissionChecker:
    def test_default_read_is_allow(self) -> None:
        checker = PermissionChecker()
        assert checker.check("read_file", "read") == Decision.ALLOW

    def test_default_write_is_ask(self) -> None:
        checker = PermissionChecker()
        assert checker.check("write_file", "write") == Decision.ASK

    def test_default_dangerous_is_ask(self) -> None:
        checker = PermissionChecker()
        assert checker.check("bash", "dangerous") == Decision.ASK

    def test_tool_name_rule_overrides_default(self) -> None:
        checker = PermissionChecker(rules=[
            PermissionRule(tool_name="bash", decision=Decision.ALLOW),
        ])
        assert checker.check("bash", "dangerous") == Decision.ALLOW

    def test_risk_level_rule(self) -> None:
        checker = PermissionChecker(rules=[
            PermissionRule(risk_level="write", decision=Decision.ALLOW),
        ])
        assert checker.check("write_file", "write") == Decision.ALLOW
        assert checker.check("edit_file", "write") == Decision.ALLOW

    def test_tool_name_takes_priority_over_risk(self) -> None:
        checker = PermissionChecker(rules=[
            PermissionRule(risk_level="dangerous", decision=Decision.ALLOW),
            PermissionRule(tool_name="bash", decision=Decision.DENY),
        ])
        assert checker.check("bash", "dangerous") == Decision.DENY

    def test_allow_always(self) -> None:
        checker = PermissionChecker()
        checker.allow_always("bash")
        assert checker.check("bash", "dangerous") == Decision.ALLOW

    def test_deny_always(self) -> None:
        checker = PermissionChecker()
        checker.deny_always("read_file")
        assert checker.check("read_file", "read") == Decision.DENY

    def test_remove_tool_rule(self) -> None:
        checker = PermissionChecker()
        checker.allow_always("bash")
        assert checker.check("bash", "dangerous") == Decision.ALLOW
        checker.remove_tool_rule("bash")
        assert checker.check("bash", "dangerous") == Decision.ASK


class TestPermissionEdgeCases:
    def test_unknown_risk_level_defaults_to_ask(self) -> None:
        checker = PermissionChecker()
        assert checker.check("custom_tool", "unknown_level") == Decision.ASK

    def test_multiple_rules_last_wins_for_same_tool(self) -> None:
        checker = PermissionChecker()
        checker.allow_always("bash")
        checker.deny_always("bash")
        assert checker.check("bash", "dangerous") == Decision.DENY

    def test_risk_rule_does_not_affect_other_risk(self) -> None:
        checker = PermissionChecker(rules=[
            PermissionRule(risk_level="write", decision=Decision.ALLOW),
        ])
        assert checker.check("bash", "dangerous") == Decision.ASK

    def test_empty_rules(self) -> None:
        checker = PermissionChecker(rules=[])
        assert checker.check("read_file", "read") == Decision.ALLOW
        assert checker.check("bash", "dangerous") == Decision.ASK

    def test_remove_nonexistent_rule_noop(self) -> None:
        checker = PermissionChecker()
        checker.remove_tool_rule("nonexistent")  # should not raise


class TestAgentWithPermissions:
    async def test_deny_blocks_execution(self, config: ModelConfig, bus: MessageBus) -> None:
        reg = ToolRegistry()
        reg.register(BashTool())
        checker = PermissionChecker()
        checker.deny_always("bash")
        agent = Agent(config=config, bus=bus, registry=reg, permission_checker=checker)

        collected: list = []
        bus.on("tool_call_start", lambda m: collected.append(m))

        tc = ToolCallInfo(id="c1", name="bash", arguments=json.dumps({"command": "echo hi"}))
        result = await agent._run_one_tool(tc)
        assert "Permission denied" in result
        assert not any(isinstance(e, ToolCallStart) for e in collected)

    async def test_allow_executes(self, config: ModelConfig, bus: MessageBus) -> None:
        reg = ToolRegistry()
        reg.register(BashTool())
        checker = PermissionChecker()
        checker.allow_always("bash")
        agent = Agent(config=config, bus=bus, registry=reg, permission_checker=checker)

        collected: list = []
        for t in ("tool_call_start", "tool_call_end"):
            bus.on(t, lambda m, c=collected: c.append(m))

        tc = ToolCallInfo(id="c1", name="bash", arguments=json.dumps({"command": "echo hello"}))
        result = await agent._run_one_tool(tc)
        assert "hello" in result
        assert any(isinstance(e, ToolCallStart) for e in collected)
        assert any(isinstance(e, ToolCallEnd) for e in collected)

    async def test_ask_with_grant(self, config: ModelConfig, bus: MessageBus) -> None:
        """ASK → PermissionRequest emitted → handler grants → tool executes."""
        reg = ToolRegistry()
        reg.register(BashTool())
        checker = PermissionChecker()  # default: dangerous → ask
        agent = Agent(config=config, bus=bus, registry=reg, permission_checker=checker)

        perm_requests: list = []
        bus.on("permission_request", lambda m: perm_requests.append(m))

        async def auto_grant(msg: PermissionRequest) -> None:
            await bus.emit(PermissionResponse(
                tool_call_id=msg.tool_call_id, granted=True,
            ))
        bus.on("permission_request", auto_grant)

        tc = ToolCallInfo(id="c1", name="bash", arguments=json.dumps({"command": "echo hi"}))
        result = await agent._run_one_tool(tc)
        assert len(perm_requests) == 1
        assert "hi" in result

    async def test_ask_with_deny(self, config: ModelConfig, bus: MessageBus) -> None:
        """ASK → PermissionRequest → handler denies → permission denied."""
        reg = ToolRegistry()
        reg.register(BashTool())
        checker = PermissionChecker()
        agent = Agent(config=config, bus=bus, registry=reg, permission_checker=checker)

        async def auto_deny(msg: PermissionRequest) -> None:
            await bus.emit(PermissionResponse(
                tool_call_id=msg.tool_call_id, granted=False,
            ))
        bus.on("permission_request", auto_deny)

        tc = ToolCallInfo(id="c1", name="bash", arguments=json.dumps({"command": "echo hi"}))
        result = await agent._run_one_tool(tc)
        assert "Permission denied" in result

    async def test_read_tool_no_permission_event(self, config: ModelConfig, bus: MessageBus, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("content\n")
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        checker = PermissionChecker()  # default: read → allow
        agent = Agent(config=config, bus=bus, registry=reg, permission_checker=checker)

        perm_requests: list = []
        bus.on("permission_request", lambda m: perm_requests.append(m))

        tc = ToolCallInfo(id="c1", name="read_file", arguments=json.dumps({"path": str(f)}))
        result = await agent._run_one_tool(tc)
        assert len(perm_requests) == 0
        assert "content" in result
