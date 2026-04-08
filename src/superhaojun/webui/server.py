"""FastAPI application: WebSocket for real-time chat, REST for state queries."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..agent import Agent
from ..bus import MessageBus
from ..messages import (
    AgentEnd, AgentStart, Error, PermissionRequest, PermissionResponse,
    TextDelta, ToolCallEnd, ToolCallStart, TurnEnd, TurnStart,
    message_to_dict,
)

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class WebUIState:
    """Shared mutable state for the WebUI server."""

    def __init__(self, agent: Agent, bus: MessageBus) -> None:
        self.agent = agent
        self.bus = bus
        self.connections: list[WebSocket] = []
        self.hook_log: list[dict[str, Any]] = []
        self.agent_history: list[dict[str, Any]] = []
        self._setup_bus_forwarders()

    def _setup_bus_forwarders(self) -> None:
        """Forward MessageBus events to all WebSocket connections."""
        for msg_type in (
            "text_delta", "tool_call_start", "tool_call_end",
            "permission_request", "turn_start", "turn_end",
            "agent_start", "agent_end", "error",
        ):
            self.bus.on(msg_type, self._make_forwarder(msg_type))

    def _make_forwarder(self, msg_type: str):
        async def forward(msg: Any) -> None:
            payload = message_to_dict(msg)
            text = json.dumps(payload, ensure_ascii=False, default=str)
            dead: list[WebSocket] = []
            for ws in self.connections:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.connections.remove(ws)
        return forward

    async def broadcast(self, data: dict[str, Any]) -> None:
        text = json.dumps(data, ensure_ascii=False, default=str)
        dead: list[WebSocket] = []
        for ws in self.connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)


def create_app(agent: Agent, bus: MessageBus, **extras: Any) -> FastAPI:
    """Create the FastAPI app wired to an Agent + MessageBus."""
    app = FastAPI(title="SuperHaojun WebUI", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    state = WebUIState(agent=agent, bus=bus)
    app.state.ui = state

    # Store extras (mcp_manager, hook_registry, etc.)
    for k, v in extras.items():
        setattr(app.state, k, v)

    # ── WebSocket: bidirectional real-time ──

    @app.websocket("/api/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        state.connections.append(ws)
        logger.info("WebSocket connected (%d total)", len(state.connections))

        # Send initial state snapshot
        await ws.send_text(json.dumps({
            "type": "init",
            "tools": _get_tools_list(state),
            "messages": _get_messages(state),
            "token_usage": _get_token_usage(state),
        }, ensure_ascii=False, default=str))

        try:
            while True:
                raw = await ws.receive_text()
                data = json.loads(raw)
                await _handle_ws_message(state, data)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.warning("WebSocket error: %s", exc)
        finally:
            if ws in state.connections:
                state.connections.remove(ws)
            logger.info("WebSocket disconnected (%d remaining)", len(state.connections))

    # ── REST: state queries ──

    @app.get("/api/messages")
    async def get_messages() -> list[dict[str, Any]]:
        return _get_messages(state)

    @app.get("/api/tools")
    async def get_tools() -> list[dict[str, Any]]:
        return _get_tools_list(state)

    @app.get("/api/mcp/status")
    async def get_mcp_status() -> list[dict[str, Any]]:
        mgr = getattr(app.state, "mcp_manager", None)
        return mgr.get_status() if mgr else []

    @app.post("/api/mcp/{name}/{action}")
    async def mcp_action(name: str, action: str) -> dict[str, Any]:
        mgr = getattr(app.state, "mcp_manager", None)
        if not mgr:
            return {"ok": False, "error": "No MCP manager"}
        if action == "enable":
            ok = await mgr.enable(name)
        elif action == "disable":
            ok = await mgr.disable(name)
        elif action == "reconnect":
            ok = await mgr.reconnect(name)
        else:
            return {"ok": False, "error": f"Unknown action: {action}"}
        return {"ok": ok}

    @app.get("/api/hooks")
    async def get_hooks() -> list[dict[str, Any]]:
        registry = getattr(app.state, "hook_registry", None)
        if not registry:
            return []
        return [
            {
                "event": r.event.value,
                "tool_pattern": r.tool_pattern,
                "hook_type": r.hook_type.value,
                "command": r.command,
                "priority": r.priority,
                "enabled": r.enabled,
            }
            for r in registry.list_hooks()
        ]

    @app.get("/api/hooks/log")
    async def get_hook_log() -> list[dict[str, Any]]:
        return state.hook_log[-100:]

    @app.get("/api/agents/history")
    async def get_agent_history() -> list[dict[str, Any]]:
        return state.agent_history[-50:]

    @app.get("/api/diagnostics")
    async def get_diagnostics() -> list[dict[str, Any]]:
        registry = getattr(app.state, "diagnostic_registry", None)
        if not registry:
            return []
        results = []
        for file_path, diags in registry.get_all().items():
            for d in diags:
                results.append({
                    "file": file_path,
                    "line": d.line,
                    "character": d.character,
                    "message": d.message,
                    "severity": d.severity,
                    "provider": d.provider,
                })
        return results

    @app.get("/api/token-usage")
    async def get_token_usage() -> dict[str, Any]:
        return _get_token_usage(state)

    @app.get("/api/config")
    async def get_config() -> dict[str, Any]:
        cfg = state.agent.config
        return {
            "model_id": cfg.model_id,
            "base_url": cfg.base_url,
            "provider": cfg.provider,
        }

    @app.get("/api/config/models")
    async def get_models() -> list[dict[str, Any]]:
        """List all model profiles with active flag."""
        registry = getattr(app.state, "model_registry", None)
        if registry is None:
            cfg = state.agent.config
            return [{
                "key": "default",
                "name": cfg.model_id,
                "model_id": cfg.model_id,
                "base_url": cfg.base_url,
                "provider": cfg.provider,
                "active": True,
            }]
        return registry.list_profiles()

    @app.post("/api/config/models/{key}/activate")
    async def activate_model(key: str) -> dict[str, Any]:
        """Switch the active model profile."""
        registry = getattr(app.state, "model_registry", None)
        if registry is None:
            return {"ok": False, "error": "No model registry available"}
        try:
            new_config = registry.switch(key)
            state.agent.switch_model(new_config)
            # Broadcast model change to all WS clients
            await state.broadcast({
                "type": "model_changed",
                "key": key,
                "model_id": new_config.model_id,
                "provider": new_config.provider,
                "base_url": new_config.base_url,
            })
            return {"ok": True, "active": key, "model_id": new_config.model_id}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    @app.get("/api/commands")
    async def get_commands() -> list[dict[str, str]]:
        """List available slash commands for autocomplete."""
        cmd_registry = getattr(app.state, "command_registry", None)
        if cmd_registry is None:
            return []
        return [
            {"name": cmd.name, "description": cmd.description}
            for cmd in sorted(cmd_registry.all(), key=lambda c: c.name)
        ]

    # Serve frontend static files (if built)
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


# ── WebSocket message handlers ──

async def _handle_ws_message(state: WebUIState, data: dict[str, Any]) -> None:
    msg_type = data.get("type", "")

    if msg_type == "user_message":
        text = data.get("text", "").strip()
        if text:
            asyncio.create_task(_run_agent_message(state, text))

    elif msg_type == "permission_response":
        tool_call_id = data.get("tool_call_id", "")
        granted = data.get("granted", False)
        await state.bus.emit(PermissionResponse(
            tool_call_id=tool_call_id, granted=granted,
        ))

    elif msg_type == "interrupt":
        pass  # TODO: implement interrupt

    elif msg_type == "ping":
        await state.broadcast({"type": "pong"})


async def _run_agent_message(state: WebUIState, text: str) -> None:
    try:
        await state.agent.handle_user_message(text)
    except Exception as exc:
        logger.error("Agent error: %s", exc)
        await state.broadcast({
            "type": "error",
            "message": str(exc),
        })


def _get_messages(state: WebUIState) -> list[dict[str, Any]]:
    return [
        {
            "role": m.role,
            "content": m.content,
            "tool_calls": m.tool_calls,
            "tool_call_id": m.tool_call_id,
            "name": m.name,
        }
        for m in state.agent.messages
    ]


def _get_tools_list(state: WebUIState) -> list[dict[str, Any]]:
    tools = []
    for td in state.agent.registry.to_openai_tools():
        fn = td.get("function", {})
        tools.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
        })
    return tools


def _get_token_usage(state: WebUIState) -> dict[str, Any]:
    msg_count = len(state.agent.messages)
    # Rough estimation: ~4 chars per token
    char_count = sum(len(m.content or "") for m in state.agent.messages)
    est_tokens = char_count // 4
    return {
        "message_count": msg_count,
        "estimated_tokens": est_tokens,
        "max_tokens": 128000,
        "compaction_count": 0,
    }
