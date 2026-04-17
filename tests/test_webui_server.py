"""Tests for WebUI server chat behavior."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from superhaojun.agent import Agent
from superhaojun.bus import MessageBus
from superhaojun.config import ModelConfig
from superhaojun.extensions.runtime import ExtensionRuntime
from superhaojun.messages import AgentEnd, AgentStart, PermissionRequest
from superhaojun.prompt.builder import SystemPromptBuilder
from superhaojun.tools.base import Tool
from superhaojun.webui.server import WebUIState, _handle_ws_message, create_app


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


class _ToggleTool(Tool):
    @property
    def name(self) -> str:
        return "toggle_tool"

    @property
    def description(self) -> str:
        return "Tool used to verify WebUI toggles."

    @property
    def parameters(self) -> dict[str, object]:
        return {"type": "object", "properties": {}}

    @property
    def risk_level(self) -> str:
        return "write"

    async def execute(self, **kwargs: object) -> str:
        return "ok"


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


def test_extension_state_endpoint_toggles_runtime_and_prompt(tmp_path: Path, agent: Agent, bus: MessageBus) -> None:
    (tmp_path / "SUPERHAOJUN.md").write_text("Use dataclasses.", encoding="utf-8")
    brand = tmp_path / ".haojun"
    brand.mkdir()

    runtime = ExtensionRuntime(working_dir=tmp_path, config_path=brand / "extensions.json")
    builder = SystemPromptBuilder(working_dir=str(tmp_path), extension_runtime=runtime)
    agent.prompt_builder = builder

    app = create_app(agent, bus, extension_runtime=runtime)
    client = TestClient(app)
    extension_id = runtime.list_extensions()[0]["id"]

    assert "Use dataclasses." in builder.build()

    response = client.post("/api/extensions/state", json={"id": extension_id, "enabled": False})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert any(
        item["id"] == extension_id and item["enabled"] is False
        for item in payload["extensions"]
    )

    builder.invalidate()
    assert "Use dataclasses." not in builder.build()


def test_tool_state_endpoint_toggles_registry(agent: Agent, bus: MessageBus) -> None:
    agent.registry.register(_ToggleTool())

    app = create_app(agent, bus)
    client = TestClient(app)

    response = client.post("/api/tools/state", json={"name": "toggle_tool", "enabled": False})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert any(
        item["name"] == "toggle_tool" and item["enabled"] is False
        for item in payload["tools"]
    )
    assert agent.registry.get("toggle_tool") is None
    assert agent.registry.get_registered("toggle_tool") is not None


def test_websocket_permission_flow_round_trips_response(agent: Agent, bus: MessageBus) -> None:
    decisions: list[bool] = []

    async def permission_gate(_: str) -> None:
        await bus.emit(AgentStart())
        waiter = bus.expect("permission_response", "call-1")
        await bus.emit(
            PermissionRequest(
                tool_call_id="call-1",
                tool_name="write_file",
                arguments={"path": "/tmp/approval.txt", "content": "ok"},
                risk_level="write",
            )
        )
        response = await asyncio.wait_for(waiter, timeout=1)
        decisions.append(bool(response.granted))
        await bus.emit(AgentEnd())

    agent.handle_user_message = permission_gate  # type: ignore[method-assign]

    app = create_app(agent, bus)
    client = TestClient(app)

    with client.websocket_connect("/api/ws") as ws:
        init = ws.receive_json()
        assert init["type"] == "init"

        ws.send_json({"type": "user_message", "text": "create the file"})

        permission_request = None
        while permission_request is None:
            message = ws.receive_json()
            if message["type"] == "permission_request":
                permission_request = message

        assert permission_request["tool_call_id"] == "call-1"
        assert permission_request["tool_name"] == "write_file"
        assert permission_request["risk_level"] == "write"

        ws.send_json(
            {"type": "permission_response", "tool_call_id": "call-1", "granted": True}
        )

        seen_agent_end = False
        while not seen_agent_end:
            message = ws.receive_json()
            seen_agent_end = message["type"] == "agent_end"

    assert decisions == [True]
