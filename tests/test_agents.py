"""Tests for agents v2 — SubAgentResult, Coordinator LLM planning, /agents command."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from superhaojun.agents.sub_agent import SubAgent, SubAgentResult
from superhaojun.agents.agent_tool import AgentTool
from superhaojun.agents.coordinator import Coordinator, TaskSpec, TaskResult
from superhaojun.agents.commands import AgentsCommand
from superhaojun.commands.base import CommandContext
from superhaojun.config import ModelConfig


def _config():
    return ModelConfig(provider="openai", model_id="gpt-5.4", base_url="https://example.com/v1", api_key="test-key")


# ── SubAgentResult ──


class TestSubAgentResult:
    def test_success(self):
        r = SubAgentResult(output="done", tool_calls_made=2, turns_used=3, success=True)
        assert r.success is True
        assert r.output == "done"
        assert r.tool_calls_made == 2

    def test_failure(self):
        r = SubAgentResult(output="partial", success=False, error="timeout")
        assert r.success is False
        assert r.error == "timeout"

    def test_frozen(self):
        r = SubAgentResult(output="x")
        with pytest.raises(AttributeError):
            r.output = "y"  # type: ignore[misc]


# ── SubAgent ──


class TestSubAgent:
    async def test_run_success(self):
        sub = SubAgent(config=_config())
        with patch("superhaojun.agent.Agent.handle_user_message", new_callable=AsyncMock), \
             patch("superhaojun.agent.Agent.close", new_callable=AsyncMock):
            result = await sub.run("test task")
        assert isinstance(result, SubAgentResult)
        assert result.success is True

    async def test_run_reports_turns_used_from_agent_runtime(self):
        class FakeTurnRuntime:
            def __init__(self) -> None:
                self.turn_index = 0

        class FakeAgent:
            def __init__(self, **kwargs):
                self.turn_runtime = FakeTurnRuntime()

            async def handle_user_message(self, user_input: str) -> None:
                self.turn_runtime.turn_index = 3

            async def close(self) -> None:
                return None

        sub = SubAgent(config=_config())
        with patch("superhaojun.agent.Agent", FakeAgent):
            result = await sub.run("test task")

        assert result.turns_used == 3

    async def test_run_with_progress(self):
        collected = []
        sub = SubAgent(config=_config(), on_progress=lambda t: collected.append(t))
        with patch("superhaojun.agent.Agent.handle_user_message", new_callable=AsyncMock), \
             patch("superhaojun.agent.Agent.close", new_callable=AsyncMock):
            result = await sub.run("test task")
        assert result.success is True

    async def test_run_error(self):
        sub = SubAgent(config=_config())
        with patch("superhaojun.agent.Agent.handle_user_message", new_callable=AsyncMock, side_effect=RuntimeError("boom")), \
             patch("superhaojun.agent.Agent.close", new_callable=AsyncMock):
            result = await sub.run("test task")
        assert result.success is False
        assert "boom" in result.error


# ── TaskResult ──


class TestTaskResult:
    def test_from_sub_result_success(self):
        sub = SubAgentResult(output="done", tool_calls_made=1, turns_used=2, success=True)
        tr = TaskResult.from_sub_result("t1", sub)
        assert tr.task_id == "t1"
        assert tr.output == "done"
        assert tr.success is True

    def test_from_sub_result_failure(self):
        sub = SubAgentResult(output="partial", success=False, error="crash")
        tr = TaskResult.from_sub_result("t1", sub)
        assert tr.success is False
        assert "crash" in tr.output


# ── Coordinator ──


class TestCoordinator:
    async def test_run_empty(self):
        coord = Coordinator(config=_config())
        results = await coord.run([])
        assert results == []

    async def test_run_single(self):
        coord = Coordinator(config=_config())
        tasks = [TaskSpec(task_id="t1", description="Do stuff")]
        with patch("superhaojun.agent.Agent.handle_user_message", new_callable=AsyncMock), \
             patch("superhaojun.agent.Agent.close", new_callable=AsyncMock):
            results = await coord.run(tasks)
        assert len(results) == 1
        assert results[0].task_id == "t1"
        assert results[0].success is True

    async def test_run_multiple(self):
        coord = Coordinator(config=_config(), max_concurrent=2)
        tasks = [
            TaskSpec(task_id="t1", description="Task 1"),
            TaskSpec(task_id="t2", description="Task 2"),
            TaskSpec(task_id="t3", description="Task 3"),
        ]
        with patch("superhaojun.agent.Agent.handle_user_message", new_callable=AsyncMock), \
             patch("superhaojun.agent.Agent.close", new_callable=AsyncMock):
            results = await coord.run(tasks)
        assert len(results) == 3
        assert all(r.success for r in results)

    async def test_run_sequential(self):
        coord = Coordinator(config=_config())
        tasks = [
            TaskSpec(task_id="t1", description="First"),
            TaskSpec(task_id="t2", description="Second"),
        ]
        with patch("superhaojun.agent.Agent.handle_user_message", new_callable=AsyncMock), \
             patch("superhaojun.agent.Agent.close", new_callable=AsyncMock):
            results = await coord.run_sequential(tasks)
        assert len(results) == 2

    async def test_run_with_llm_planning(self):
        coord = Coordinator(config=_config())
        # Mock the LLM planning response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps([
            {"task_id": "t1", "description": "Analyze code"},
            {"task_id": "t2", "description": "Write tests"},
        ])
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with patch("openai.AsyncOpenAI", return_value=mock_client), \
             patch("httpx.AsyncClient"), \
             patch("superhaojun.agent.Agent.handle_user_message", new_callable=AsyncMock), \
             patch("superhaojun.agent.Agent.close", new_callable=AsyncMock):
            results = await coord.run_with_llm_planning("Refactor the codebase")
        assert len(results) == 2
        assert results[0].task_id == "t1"

    async def test_run_with_llm_planning_error(self):
        coord = Coordinator(config=_config())
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API error"))
        mock_client.close = AsyncMock()

        with patch("openai.AsyncOpenAI", return_value=mock_client), \
             patch("httpx.AsyncClient"):
            results = await coord.run_with_llm_planning("Fail")
        assert len(results) == 1
        assert results[0].success is False
        assert "Planning failed" in results[0].output


# ── AgentTool ──


class TestAgentTool:
    def test_properties(self):
        tool = AgentTool(config=_config(), registry=MagicMock())
        assert tool.name == "agent"
        assert tool.risk_level == "read"
        assert tool.is_concurrent_safe is True

    async def test_execute_no_task(self):
        tool = AgentTool(config=_config(), registry=MagicMock())
        result = await tool.execute()
        assert "Error" in result

    async def test_execute_success(self):
        tool = AgentTool(config=_config(), registry=MagicMock())
        with patch("superhaojun.agent.Agent.handle_user_message", new_callable=AsyncMock), \
             patch("superhaojun.agent.Agent.close", new_callable=AsyncMock):
            result = await tool.execute(task="Do something")
        assert isinstance(result, str)

    async def test_execute_delegates_to_sub_agent(self):
        tool = AgentTool(config=_config(), registry=MagicMock())
        mock_result = SubAgentResult(output="sub output", success=True)
        with patch.object(SubAgent, "run", new_callable=AsyncMock, return_value=mock_result):
            result = await tool.execute(task="Test")
        assert result == "sub output"


# ── AgentsCommand ──


class TestAgentsCommand:
    def _ctx(self, coordinator=None):
        ctx = CommandContext(agent=MagicMock())
        ctx.coordinator = coordinator  # type: ignore[attr-defined]
        return ctx

    async def test_list_no_coordinator(self):
        cmd = AgentsCommand()
        result = await cmd.execute("list", self._ctx())
        assert "No coordinator" in result

    async def test_list_with_coordinator(self):
        coord = Coordinator(config=_config(), max_concurrent=3, max_turns_per_task=5)
        cmd = AgentsCommand()
        result = await cmd.execute("list", self._ctx(coord))
        assert "max_concurrent=3" in result

    async def test_run_no_goal(self):
        coord = Coordinator(config=_config())
        cmd = AgentsCommand()
        result = await cmd.execute("run", self._ctx(coord))
        assert "Usage" in result

    async def test_run_with_goal(self):
        coord = Coordinator(config=_config())
        mock_results = [TaskResult(task_id="t1", output="done", success=True)]
        with patch.object(coord, "run_with_llm_planning", new_callable=AsyncMock, return_value=mock_results):
            cmd = AgentsCommand()
            result = await cmd.execute("run Refactor code", self._ctx(coord))
        assert "Completed 1 subtasks" in result
        assert "✓" in result

    async def test_unknown_subcmd(self):
        coord = Coordinator(config=_config())
        cmd = AgentsCommand()
        result = await cmd.execute("badcmd", self._ctx(coord))
        assert "Unknown" in result

    def test_name_and_description(self):
        cmd = AgentsCommand()
        assert cmd.name == "agents"
        assert "Multi-agent" in cmd.description
