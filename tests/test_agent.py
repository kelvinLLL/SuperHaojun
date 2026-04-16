"""Tests for agent module."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from superhaojun.agent import Agent, ToolCallInfo
from superhaojun.bus import MessageBus
from superhaojun.conversation import ChatMessage, ConversationState
from superhaojun.config import ModelConfig
from superhaojun.messages import (
    AgentEnd, AgentStart, TextDelta, ToolCallEnd, ToolCallStart,
    TurnEnd, TurnStart,
)
from superhaojun.tools import ReadFileTool, ToolRegistry


@pytest.fixture
def config() -> ModelConfig:
    return ModelConfig(
        provider="openai",
        model_id="gpt-4o",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus()


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ReadFileTool())
    return reg


@pytest.fixture
def agent(config: ModelConfig, bus: MessageBus) -> Agent:
    return Agent(config=config, bus=bus)


@pytest.fixture
def agent_with_tools(config: ModelConfig, bus: MessageBus, registry: ToolRegistry) -> Agent:
    return Agent(config=config, bus=bus, registry=registry)


def _collect_from_bus(bus: MessageBus) -> list:
    """Register catch-all handlers that collect all messages."""
    collected: list = []
    for msg_type in ("text_delta", "tool_call_start", "tool_call_end",
                     "turn_start", "turn_end", "agent_start", "agent_end",
                     "error", "permission_request"):
        bus.on(msg_type, lambda m, c=collected: c.append(m))
    return collected


class TestAgent:
    def test_initial_state(self, agent: Agent) -> None:
        assert agent.messages == []
        assert isinstance(agent.conversation, ConversationState)
        assert agent.conversation.messages is agent.messages
        # prompt_builder is None and system_prompt is empty for test agent
        assert agent.prompt_builder is None

    def test_reset(self, agent: Agent) -> None:
        agent.messages.append(ChatMessage(role="user", content="hello"))
        agent.messages.append(ChatMessage(role="assistant", content="hi"))
        assert len(agent.messages) == 2
        agent.reset()
        assert agent.messages == []

    def test_build_messages(self, agent: Agent) -> None:
        agent.messages.append(ChatMessage(role="user", content="hello"))
        agent.messages.append(ChatMessage(role="assistant", content="hi"))
        msgs = agent._build_messages()
        assert msgs[0]["role"] == "system"
        assert msgs[1] == {"role": "user", "content": "hello"}
        assert msgs[2] == {"role": "assistant", "content": "hi"}
        assert len(msgs) == 3

    def test_build_messages_empty(self, agent: Agent) -> None:
        msgs = agent._build_messages()
        assert len(msgs) == 1
        assert msgs[0]["role"] == "system"

    def test_custom_system_prompt(self, config: ModelConfig, bus: MessageBus) -> None:
        a = Agent(config=config, bus=bus, system_prompt="Custom system prompt")
        msgs = a._build_messages()
        assert msgs[0]["content"] == "Custom system prompt"

    def test_client_lazy_init(self, agent: Agent) -> None:
        assert agent._client is None
        _ = agent.client
        assert agent._client is not None

    async def test_close(self, agent: Agent) -> None:
        _ = agent.client
        assert agent._client is not None
        await agent.close()
        assert agent._client is None

    async def test_close_idempotent(self, agent: Agent) -> None:
        await agent.close()
        assert agent._client is None


class TestBuildMessagesWithTools:
    def test_tool_call_message(self, agent: Agent) -> None:
        agent.messages.append(ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'},
            }],
        ))
        agent.messages.append(ChatMessage(
            role="tool",
            content="file contents",
            tool_call_id="call_1",
            name="read_file",
        ))
        msgs = agent._build_messages()
        assert msgs[1]["role"] == "assistant"
        assert "tool_calls" in msgs[1]
        assert msgs[2]["role"] == "tool"
        assert msgs[2]["tool_call_id"] == "call_1"


# ── Helpers for mocking streaming ──

def _make_chunk(content: str | None = None, finish_reason: str | None = None,
                tool_calls: list[Any] | None = None):
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls

    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason

    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


class _AsyncStreamIter:
    def __init__(self, chunks: list):
        self._chunks = chunks
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


class TestMessageBusIntegration:
    async def test_text_only_messages(self, agent: Agent, bus: MessageBus) -> None:
        """Text-only response emits AgentStart, TurnStart, TextDelta*, TurnEnd, AgentEnd."""
        collected = _collect_from_bus(bus)

        chunks = [
            _make_chunk(content="Hello"),
            _make_chunk(content=" world"),
            _make_chunk(finish_reason="stop"),
        ]

        mock_stream = _AsyncStreamIter(chunks)
        with patch.object(agent, "_client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)
            agent._client = mock_client

            await agent.handle_user_message("hi")

        assert isinstance(collected[0], AgentStart)
        assert isinstance(collected[1], TurnStart)
        text_deltas = [e for e in collected if isinstance(e, TextDelta)]
        assert "".join(d.text for d in text_deltas) == "Hello world"
        assert isinstance(collected[-2], TurnEnd)
        assert isinstance(collected[-1], AgentEnd)
        assert agent.messages[-1].role == "assistant"
        assert agent.messages[-1].content == "Hello world"

    async def test_tool_call_messages(self, agent_with_tools: Agent, bus: MessageBus, tmp_path) -> None:
        """Tool call emits ToolCallStart + ToolCallEnd events and loops back to LLM."""
        collected = _collect_from_bus(bus)

        test_file = tmp_path / "test.txt"
        test_file.write_text("hello\n")

        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "call_abc"
        tc_delta.function = MagicMock()
        tc_delta.function.name = "read_file"
        tc_delta.function.arguments = json.dumps({"path": str(test_file)})

        chunks_round1 = [
            _make_chunk(tool_calls=[tc_delta]),
            _make_chunk(finish_reason="tool_calls"),
        ]

        chunks_round2 = [
            _make_chunk(content="File says hello"),
            _make_chunk(finish_reason="stop"),
        ]

        call_count = 0
        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _AsyncStreamIter(chunks_round1)
            return _AsyncStreamIter(chunks_round2)

        with patch.object(agent_with_tools, "_client") as mock_client:
            mock_client.chat.completions.create = mock_create
            agent_with_tools._client = mock_client

            await agent_with_tools.handle_user_message("read my file")

        assert call_count == 2
        tool_starts = [e for e in collected if isinstance(e, ToolCallStart)]
        tool_ends = [e for e in collected if isinstance(e, ToolCallEnd)]
        assert len(tool_starts) == 1
        assert tool_starts[0].tool_name == "read_file"
        assert len(tool_ends) == 1
        assert "hello" in tool_ends[0].result

        text_deltas = [e for e in collected if isinstance(e, TextDelta)]
        assert "File says hello" in "".join(d.text for d in text_deltas)

        roles = [m.role for m in agent_with_tools.messages]
        assert roles == ["user", "assistant", "tool", "assistant"]

    async def test_unknown_tool_returns_error(self, agent_with_tools: Agent) -> None:
        result = await agent_with_tools._run_one_tool(
            ToolCallInfo(id="call_1", name="nonexistent", arguments="{}")
        )
        assert "Error: unknown tool" in result

    async def test_invalid_arguments_returns_error(self, agent_with_tools: Agent) -> None:
        result = await agent_with_tools._run_one_tool(
            ToolCallInfo(id="call_1", name="read_file", arguments="not json")
        )
        assert "Error: invalid tool arguments" in result

    async def test_concurrent_tool_calls(self, bus: MessageBus, tmp_path) -> None:
        config = ModelConfig(
            provider="openai", model_id="gpt-4o",
            base_url="https://api.openai.com/v1", api_key="sk-test",
        )
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        agent = Agent(config=config, bus=bus, registry=reg)
        collected = _collect_from_bus(bus)

        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("aaa\n")
        f2.write_text("bbb\n")

        calls = [
            ToolCallInfo(id="c1", name="read_file", arguments=json.dumps({"path": str(f1)})),
            ToolCallInfo(id="c2", name="read_file", arguments=json.dumps({"path": str(f2)})),
        ]

        await agent._execute_tool_calls(calls)

        tool_msgs = [m for m in agent.messages if m.role == "tool"]
        assert len(tool_msgs) == 2
        assert any("aaa" in (m.content or "") for m in tool_msgs)
        assert any("bbb" in (m.content or "") for m in tool_msgs)

        tool_starts = [e for e in collected if isinstance(e, ToolCallStart)]
        tool_ends = [e for e in collected if isinstance(e, ToolCallEnd)]
        assert len(tool_starts) == 2
        assert len(tool_ends) == 2
