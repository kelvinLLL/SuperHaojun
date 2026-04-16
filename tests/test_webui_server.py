"""Tests for WebUI server chat behavior."""

from __future__ import annotations

import asyncio
import json

import pytest

from superhaojun.agent import Agent
from superhaojun.bus import MessageBus
from superhaojun.config import ModelConfig
from superhaojun.webui.server import WebUIState, _handle_ws_message


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


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


@pytest.mark.asyncio
async def test_user_message_tracks_active_webui_agent_task(agent: Agent, bus: MessageBus) -> None:
    state = WebUIState(agent=agent, bus=bus)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_handle(_: str) -> None:
        started.set()
        await release.wait()

    agent.handle_user_message = slow_handle  # type: ignore[method-assign]

    await _handle_ws_message(state, {"type": "user_message", "text": "hello"})
    await asyncio.wait_for(started.wait(), timeout=1)

    assert state.current_task is not None
    assert not state.current_task.done()

    release.set()
    await asyncio.wait_for(state.current_task, timeout=1)
    assert state.current_task is None


@pytest.mark.asyncio
async def test_interrupt_cancels_active_agent_task_and_emits_terminal_events(agent: Agent, bus: MessageBus) -> None:
    state = WebUIState(agent=agent, bus=bus)
    ws = _FakeWebSocket()
    state.connections.append(ws)  # type: ignore[arg-type]
    started = asyncio.Event()

    async def slow_handle(_: str) -> None:
        started.set()
        await asyncio.Event().wait()

    agent.handle_user_message = slow_handle  # type: ignore[method-assign]

    await _handle_ws_message(state, {"type": "user_message", "text": "hello"})
    task = state.current_task
    assert task is not None
    await asyncio.wait_for(started.wait(), timeout=1)

    await _handle_ws_message(state, {"type": "interrupt"})
    await asyncio.sleep(0)

    assert task.done()
    assert state.current_task is None
    assert agent.turn_runtime.phase == "error"
    assert agent.turn_runtime.last_error == "Interrupted by user."
    assert any(msg["type"] == "error" and msg["message"] == "Interrupted by user." for msg in ws.sent)
    assert any(msg["type"] == "agent_end" for msg in ws.sent)
