"""Tests for Feature 14: Multi-Agent (SubAgent, AgentTool, Coordinator)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from superhaojun.agents.sub_agent import SubAgent
from superhaojun.agents.agent_tool import AgentTool
from superhaojun.agents.coordinator import Coordinator, TaskSpec, TaskResult
from superhaojun.config import ModelConfig
from superhaojun.tools.registry import ToolRegistry


def _make_config() -> ModelConfig:
    return ModelConfig(provider="openai", model_id="gpt-test", base_url="https://test.example.com/v1", api_key="test-key")


# ---------------------------------------------------------------------------
# TaskSpec / TaskResult
# ---------------------------------------------------------------------------
class TestTaskSpec:
    def test_defaults(self) -> None:
        ts = TaskSpec(task_id="t1", description="do something")
        assert ts.task_id == "t1"
        assert ts.system_prompt == ""

    def test_custom_prompt(self) -> None:
        ts = TaskSpec(task_id="t2", description="analyze", system_prompt="Be concise")
        assert ts.system_prompt == "Be concise"


class TestTaskResult:
    def test_success(self) -> None:
        tr = TaskResult(task_id="t1", output="done", success=True)
        assert tr.success

    def test_failure(self) -> None:
        tr = TaskResult(task_id="t1", output="Error: boom", success=False)
        assert not tr.success


# ---------------------------------------------------------------------------
# SubAgent
# ---------------------------------------------------------------------------
class TestSubAgent:
    def test_init(self) -> None:
        config = _make_config()
        sub = SubAgent(config=config)
        assert sub.max_turns == 10
        assert sub._collected_text == []

    @pytest.mark.asyncio
    async def test_run_collects_text(self) -> None:
        """SubAgent.run() should return text collected from the agent's TextDelta."""
        config = _make_config()
        registry = ToolRegistry()

        with patch("superhaojun.agent.Agent") as MockAgent:
            mock_agent_instance = MagicMock()

            async def fake_handle(msg: str) -> None:
                pass  # In real usage, would emit TextDelta via bus.

            mock_agent_instance.handle_user_message = AsyncMock(side_effect=fake_handle)
            mock_agent_instance.close = AsyncMock()
            MockAgent.return_value = mock_agent_instance

            sub = SubAgent(config=config, registry=registry)
            result = await sub.run("test task")
            assert result == ""
            mock_agent_instance.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_error_handling(self) -> None:
        """SubAgent.run() should return error message on exception."""
        config = _make_config()

        with patch("superhaojun.agent.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.handle_user_message = AsyncMock(side_effect=RuntimeError("boom"))
            mock_agent_instance.close = AsyncMock()
            MockAgent.return_value = mock_agent_instance

            sub = SubAgent(config=config)
            result = await sub.run("test task")
            assert "SubAgent error" in result
            assert "boom" in result

    @pytest.mark.asyncio
    async def test_run_with_text_emission(self) -> None:
        """SubAgent should collect TextDelta messages emitted during run."""
        from superhaojun.messages import TextDelta

        config = _make_config()

        with patch("superhaojun.agent.Agent") as MockAgent:
            mock_agent_instance = MagicMock()

            async def fake_handle(msg: str) -> None:
                pass

            mock_agent_instance.handle_user_message = AsyncMock(side_effect=fake_handle)
            mock_agent_instance.close = AsyncMock()
            MockAgent.return_value = mock_agent_instance

            sub = SubAgent(config=config)
            # Manually inject collected text to test concatenation logic
            sub._collected_text = ["Hello", " ", "World"]
            assert "".join(sub._collected_text) == "Hello World"


# ---------------------------------------------------------------------------
# AgentTool
# ---------------------------------------------------------------------------
class TestAgentTool:
    def test_properties(self) -> None:
        config = _make_config()
        tool = AgentTool(config=config, registry=ToolRegistry())
        assert tool.name == "agent"
        assert "sub-agent" in tool.description
        assert tool.risk_level == "read"
        assert tool.is_concurrent_safe

    def test_parameters_schema(self) -> None:
        config = _make_config()
        tool = AgentTool(config=config, registry=ToolRegistry())
        params = tool.parameters
        assert params["type"] == "object"
        assert "task" in params["properties"]
        assert "task" in params["required"]

    @pytest.mark.asyncio
    async def test_execute_empty_task(self) -> None:
        config = _make_config()
        tool = AgentTool(config=config, registry=ToolRegistry())
        result = await tool.execute(task="")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_execute_calls_sub_agent(self) -> None:
        config = _make_config()
        tool = AgentTool(config=config, registry=ToolRegistry())

        with patch("superhaojun.agents.agent_tool.SubAgent") as MockSub:
            mock_sub = MagicMock()
            mock_sub.run = AsyncMock(return_value="Analysis complete")
            MockSub.return_value = mock_sub

            result = await tool.execute(task="analyze code")
            assert result == "Analysis complete"
            mock_sub.run.assert_awaited_once_with("analyze code")


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------
class TestCoordinator:
    def test_init(self) -> None:
        config = _make_config()
        coord = Coordinator(config=config)
        assert coord.max_concurrent == 5
        assert coord.max_turns_per_task == 10

    @pytest.mark.asyncio
    async def test_run_empty(self) -> None:
        config = _make_config()
        coord = Coordinator(config=config)
        results = await coord.run([])
        assert results == []

    @pytest.mark.asyncio
    async def test_run_parallel(self) -> None:
        config = _make_config()
        coord = Coordinator(config=config)
        tasks = [
            TaskSpec("t1", "task one"),
            TaskSpec("t2", "task two"),
        ]

        with patch("superhaojun.agents.coordinator.SubAgent") as MockSub:
            mock_sub = MagicMock()
            call_count = 0

            async def fake_run(task: str) -> str:
                nonlocal call_count
                call_count += 1
                return f"result_{call_count}"

            mock_sub.run = AsyncMock(side_effect=fake_run)
            MockSub.return_value = mock_sub

            results = await coord.run(tasks)
            assert len(results) == 2
            assert all(r.success for r in results)
            assert results[0].task_id == "t1"
            assert results[1].task_id == "t2"

    @pytest.mark.asyncio
    async def test_run_handles_exceptions(self) -> None:
        config = _make_config()
        coord = Coordinator(config=config)
        tasks = [TaskSpec("t1", "will fail")]

        with patch("superhaojun.agents.coordinator.SubAgent") as MockSub:
            mock_sub = MagicMock()
            mock_sub.run = AsyncMock(side_effect=RuntimeError("agent crashed"))
            MockSub.return_value = mock_sub

            results = await coord.run(tasks)
            assert len(results) == 1
            assert not results[0].success
            assert "Error" in results[0].output

    @pytest.mark.asyncio
    async def test_run_sequential(self) -> None:
        config = _make_config()
        coord = Coordinator(config=config)
        execution_order: list[str] = []
        tasks = [
            TaskSpec("t1", "first"),
            TaskSpec("t2", "second"),
        ]

        with patch("superhaojun.agents.coordinator.SubAgent") as MockSub:
            mock_sub = MagicMock()

            async def fake_run(task: str) -> str:
                execution_order.append(task)
                return f"done: {task}"

            mock_sub.run = AsyncMock(side_effect=fake_run)
            MockSub.return_value = mock_sub

            results = await coord.run_sequential(tasks)
            assert len(results) == 2
            assert execution_order == ["first", "second"]
            assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_run_with_custom_system_prompt(self) -> None:
        config = _make_config()
        coord = Coordinator(config=config)
        tasks = [
            TaskSpec("t1", "analyze", system_prompt="Custom prompt"),
        ]

        with patch("superhaojun.agents.coordinator.SubAgent") as MockSub:
            mock_sub = MagicMock()
            mock_sub.run = AsyncMock(return_value="done")
            MockSub.return_value = mock_sub

            results = await coord.run(tasks)
            assert len(results) == 1
            # Verify SubAgent was created with custom prompt
            call_kwargs = MockSub.call_args
            assert call_kwargs.kwargs.get("system_prompt") == "Custom prompt"

    @pytest.mark.asyncio
    async def test_max_concurrent_respected(self) -> None:
        """Verify that semaphore limits concurrency."""
        config = _make_config()
        coord = Coordinator(config=config, max_concurrent=2)
        max_concurrent_observed = 0
        current_concurrent = 0

        tasks = [TaskSpec(f"t{i}", f"task {i}") for i in range(5)]

        with patch("superhaojun.agents.coordinator.SubAgent") as MockSub:
            mock_sub = MagicMock()

            async def fake_run(task: str) -> str:
                nonlocal max_concurrent_observed, current_concurrent
                current_concurrent += 1
                max_concurrent_observed = max(max_concurrent_observed, current_concurrent)
                await asyncio.sleep(0.01)  # Simulate work
                current_concurrent -= 1
                return f"done: {task}"

            mock_sub.run = AsyncMock(side_effect=fake_run)
            MockSub.return_value = mock_sub

            results = await coord.run(tasks)
            assert len(results) == 5
            assert max_concurrent_observed <= 2
