"""Tests for explicit turn runtime state."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from superhaojun.agent import Agent
from superhaojun.bus import MessageBus
from superhaojun.compact.compactor import ContextCompactor
from superhaojun.conversation import ChatMessage
from superhaojun.config import ModelConfig
from superhaojun.memory.store import MemoryPromptEntry
from superhaojun.prompt.builder import SystemPromptBuilder
from superhaojun.tool_orchestration import ToolCallInfo
from superhaojun.tools.base import Tool
from superhaojun.tools.registry import ToolRegistry
from superhaojun.webui.server import WebUIState, _get_runtime_state, _get_token_usage


def _make_chunk(content: str | None = None, finish_reason: str | None = None,
                tool_calls: list[object] | None = None, usage: object | None = None):
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls

    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason

    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = usage
    return chunk


class _AsyncStreamIter:
    def __init__(self, chunks: list[object]):
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


class _EchoTool(Tool):
    @property
    def name(self) -> str:
        return "echo_tool"

    @property
    def description(self) -> str:
        return "Echo a value"

    @property
    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }

    async def execute(self, **kwargs: object) -> str:
        return f"echo:{kwargs['value']}"


class _WriteTool(Tool):
    @property
    def name(self) -> str:
        return "write_tool"

    @property
    def description(self) -> str:
        return "Write something"

    @property
    def parameters(self) -> dict[str, object]:
        return {"type": "object", "properties": {"value": {"type": "string"}}}

    @property
    def risk_level(self) -> str:
        return "write"

    async def execute(self, **kwargs: object) -> str:
        return "wrote"


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
def agent(config: ModelConfig, bus: MessageBus) -> Agent:
    return Agent(config=config, bus=bus)


@pytest.fixture
def agent_with_tools(config: ModelConfig, bus: MessageBus) -> Agent:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    registry.register(_WriteTool())
    return Agent(config=config, bus=bus, registry=registry)


@pytest.mark.asyncio
async def test_agent_tracks_turn_runtime_for_text_response(agent: Agent) -> None:
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

    assert agent.turn_runtime.turn_index == 1
    assert agent.turn_runtime.phase == "completed"
    assert agent.turn_runtime.finish_reason == "stop"
    assert agent.turn_runtime.text_chunks == ["Hello", " world"]
    assert agent.turn_runtime.buffered_tool_calls == []
    assert agent.turn_runtime.active is False
    assert agent.turn_runtime.message_count == 2
    assert agent.turn_runtime.estimated_tokens > 0


@pytest.mark.asyncio
async def test_agent_tracks_provider_usage_from_stream(agent: Agent) -> None:
    usage = MagicMock(prompt_tokens=111, completion_tokens=7, total_tokens=118)
    chunks = [
        _make_chunk(content="Hello"),
        _make_chunk(finish_reason="stop", usage=usage),
    ]
    mock_stream = _AsyncStreamIter(chunks)

    with patch.object(agent, "_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)
        agent._client = mock_client

        await agent.handle_user_message("hi")

    assert agent.turn_runtime.provider_usage == {
        "prompt_tokens": 111,
        "completion_tokens": 7,
        "total_tokens": 118,
    }


@pytest.mark.asyncio
async def test_agent_tracks_tool_queue_and_message_metrics(agent_with_tools: Agent) -> None:
    calls = [ToolCallInfo(
        id="tc1",
        name="echo_tool",
        arguments=json.dumps({"value": "a"}),
    )]

    agent_with_tools.turn_runtime.set_tool_queue(calls)
    await agent_with_tools._execute_tool_calls(calls)

    assert agent_with_tools.turn_runtime.tool_statuses == [
        {
            "id": "tc1",
            "name": "echo_tool",
            "arguments": json.dumps({"value": "a"}),
            "status": "completed",
            "detail": "echo:a",
        }
    ]
    assert agent_with_tools.turn_runtime.message_count == 1
    assert agent_with_tools.turn_runtime.estimated_tokens > 0


@pytest.mark.asyncio
async def test_agent_tracks_blocked_tool_queue_state(agent_with_tools: Agent) -> None:
    agent_with_tools.permission_checker.deny_always("write_tool")
    calls = [ToolCallInfo(
        id="tc1",
        name="write_tool",
        arguments=json.dumps({"value": "x"}),
    )]

    agent_with_tools.turn_runtime.set_tool_queue(calls)
    await agent_with_tools._execute_tool_calls(calls)

    assert agent_with_tools.turn_runtime.tool_statuses == [
        {
            "id": "tc1",
            "name": "write_tool",
            "arguments": json.dumps({"value": "x"}),
            "status": "blocked",
            "detail": "Permission denied for tool 'write_tool'",
        }
    ]


@pytest.mark.asyncio
async def test_agent_tracks_compaction_metadata(agent: Agent) -> None:
    agent.messages.extend([
        ChatMessage(role="user", content="a" * 80),
        ChatMessage(role="assistant", content="b" * 80),
        ChatMessage(role="user", content="c" * 80),
    ])
    agent.compactor = ContextCompactor(
        max_tokens=20,
        compact_threshold=0.5,
        preserve_recent=1,
        summarize_fn=AsyncMock(return_value="summary"),
        cooldown_seconds=0,
    )

    await agent._auto_compact()

    assert agent.turn_runtime.compaction_count == 1
    assert agent.turn_runtime.last_compaction == {
        "removed_count": 2,
        "preserved_count": 1,
        "pre_tokens": 60,
        "post_tokens": 21,
    }


@pytest.mark.asyncio
async def test_agent_exposes_memory_entry_metadata_in_turn_runtime(agent: Agent, tmp_path) -> None:
    builder = SystemPromptBuilder(working_dir=str(tmp_path))
    builder.set_memory_entry(MemoryPromptEntry(
        text="Memory Index\n\nLoaded Topics\n- prefs",
        loaded_entries=[{"id": "abc12345", "name": "Prefs", "category": "user", "source": "user_prefs.md", "chars": 5}],
        truncated=False,
        total_chars=32,
        index_chars=12,
        topic_chars=20,
    ))
    agent.prompt_builder = builder

    chunks = [
        _make_chunk(content="Hello"),
        _make_chunk(finish_reason="stop"),
    ]
    mock_stream = _AsyncStreamIter(chunks)

    with patch.object(agent, "_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)
        agent._client = mock_client

        await agent.handle_user_message("hi")

    assert agent.turn_runtime.memory_entry == {
        "loaded_entries": [{"id": "abc12345", "name": "Prefs", "category": "user", "source": "user_prefs.md", "chars": 5}],
        "truncated": False,
        "total_chars": 32,
        "index_chars": 12,
        "topic_chars": 20,
    }


def test_webui_runtime_snapshot_uses_agent_turn_runtime(agent: Agent, bus: MessageBus) -> None:
    class _Extensions:
        def list_extensions(self) -> list[dict[str, object]]:
            return [{"id": "instruction:SUPERHAOJUN.md", "enabled": True}]

    state = WebUIState(agent=agent, bus=bus, extension_runtime=_Extensions())
    agent.turn_runtime.phase = "streaming"
    agent.turn_runtime.turn_index = 3
    agent.turn_runtime.finish_reason = "tool_calls"
    agent.turn_runtime.message_count = 4
    agent.turn_runtime.estimated_tokens = 120
    agent.turn_runtime.compaction_count = 2
    agent.turn_runtime.set_prompt_context_metrics({
        "system_prompt_chars": 600,
        "message_chars": 180,
        "tool_call_chars": 32,
        "system_prompt_sections": [
            {"name": "identity", "chars": 220},
            {"name": "memory", "chars": 40},
        ],
    })
    agent.turn_runtime.set_provider_usage({
        "prompt_tokens": 111,
        "completion_tokens": 7,
        "total_tokens": 118,
    })

    runtime = _get_runtime_state(state)
    token_usage = _get_token_usage(state)

    assert runtime["phase"] == "streaming"
    assert runtime["turn_index"] == 3
    assert runtime["finish_reason"] == "tool_calls"
    assert runtime["message_count"] == 4
    assert runtime["estimated_tokens"] == 120
    assert runtime["compaction_count"] == 2
    assert runtime["prompt_context_metrics"] == {
        "system_prompt_chars": 600,
        "message_chars": 180,
        "tool_call_chars": 32,
        "system_prompt_sections": [
            {"name": "identity", "chars": 220},
            {"name": "memory", "chars": 40},
        ],
    }
    assert runtime["provider_usage"] == {
        "prompt_tokens": 111,
        "completion_tokens": 7,
        "total_tokens": 118,
    }
    assert runtime["extensions"] == [{"id": "instruction:SUPERHAOJUN.md", "enabled": True}]
    assert token_usage["message_count"] == 4
    assert token_usage["context_metrics"] == {
        "system_prompt_chars": 600,
        "message_chars": 180,
        "tool_call_chars": 32,
        "system_prompt_sections": [
            {"name": "identity", "chars": 220},
            {"name": "memory", "chars": 40},
        ],
    }
    assert token_usage["provider_usage"] == {
        "prompt_tokens": 111,
        "completion_tokens": 7,
        "total_tokens": 118,
    }
    assert token_usage["compaction_count"] == 2
