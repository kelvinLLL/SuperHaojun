"""FastAPI application: WebSocket for real-time chat, REST for state queries."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..agent import Agent
from ..bus import MessageBus
from ..messages import (
    AgentEnd, AgentStart, Error, PermissionRequest, PermissionResponse,
    TextDelta, ToolCallEnd, ToolCallStart, TurnEnd, TurnStart,
    message_to_dict,
)
from ..runtime import build_command_context

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class WebUIState:
    """Shared mutable state for the WebUI server."""

    def __init__(self, agent: Agent, bus: MessageBus, **extras: Any) -> None:
        self.agent = agent
        self.bus = bus
        self.extras = extras
        self.connections: list[WebSocket] = []
        self.hook_log: list[dict[str, Any]] = []
        self.agent_history: list[dict[str, Any]] = []
        self.current_task: asyncio.Task[None] | None = None
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
            if self.connections:
                await self.broadcast({
                    "type": "runtime_state",
                    "runtime": _get_runtime_state(self),
                })
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

    state = WebUIState(agent=agent, bus=bus, **extras)
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
            "runtime": _get_runtime_state(state),
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

    @app.post("/api/tools/state")
    async def set_tool_state(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        tool_name = str(payload.get("name", "")).strip()
        enabled = payload.get("enabled")
        if not tool_name or not isinstance(enabled, bool):
            return {"ok": False, "error": "Expected JSON body with string name and boolean enabled", "tools": _get_tools_list(state)}

        ok = state.agent.registry.enable(tool_name) if enabled else state.agent.registry.disable(tool_name)
        return {"ok": ok, "tools": _get_tools_list(state)}

    @app.get("/api/mcp/status")
    async def get_mcp_status() -> list[dict[str, Any]]:
        mgr = getattr(app.state, "mcp_manager", None)
        return mgr.get_status() if mgr else []

    @app.post("/api/mcp/{name}/{action}")
    async def mcp_action(name: str, action: str) -> dict[str, Any]:
        mgr = getattr(app.state, "mcp_manager", None)
        if not mgr:
            return {"ok": False, "error": "No MCP manager"}
        if action == "approve":
            ok = await mgr.approve(name)
        elif action == "deny":
            ok = await mgr.deny(name)
        elif action == "enable":
            ok = await mgr.enable(name)
        elif action == "disable":
            ok = await mgr.disable(name)
        elif action == "reconnect":
            ok = await mgr.reconnect(name)
        else:
            return {"ok": False, "error": f"Unknown action: {action}"}
        return {"ok": ok, "status": mgr.get_status()}

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

    @app.get("/api/extensions")
    async def get_extensions() -> list[dict[str, Any]]:
        runtime = getattr(app.state, "extension_runtime", None)
        if runtime is None:
            return []
        return runtime.list_extensions()

    @app.post("/api/extensions/state")
    async def set_extension_state(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        runtime = getattr(app.state, "extension_runtime", None)
        if runtime is None:
            return {"ok": False, "error": "No extension runtime", "extensions": []}

        extension_id = str(payload.get("id", "")).strip()
        enabled = payload.get("enabled")
        if not extension_id or not isinstance(enabled, bool):
            return {"ok": False, "error": "Expected JSON body with string id and boolean enabled", "extensions": runtime.list_extensions()}

        ok = runtime.enable(extension_id) if enabled else runtime.disable(extension_id)
        if ok and state.agent.prompt_builder is not None:
            state.agent.prompt_builder.invalidate()

        return {"ok": ok, "extensions": runtime.list_extensions()}

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

    @app.get("/api/runtime")
    async def get_runtime() -> dict[str, Any]:
        return _get_runtime_state(state)

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
        if not text:
            return

        # Intercept slash commands (like Claude Code's processSlashCommand)
        if text.startswith("/"):
            asyncio.create_task(_run_slash_command(state, text))
        else:
            if state.current_task is not None and not state.current_task.done():
                await state.bus.emit(Error(message="Agent is already running. Interrupt it before sending another message."))
                return
            state.current_task = asyncio.create_task(_run_agent_message(state, text))

    elif msg_type == "permission_response":
        tool_call_id = data.get("tool_call_id", "")
        granted = data.get("granted", False)
        await state.bus.emit(PermissionResponse(
            tool_call_id=tool_call_id, granted=granted,
        ))

    elif msg_type == "interrupt":
        task = state.current_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                if state.current_task is task:
                    state.current_task = None

    elif msg_type == "ping":
        await state.broadcast({"type": "pong"})


async def _run_slash_command(state: WebUIState, text: str) -> None:
    """Parse and execute a slash command, broadcasting the result."""
    # Parse: "/model list" → name="model", args="list"
    without_slash = text[1:]
    parts = without_slash.split(None, 1)
    cmd_name = parts[0] if parts else ""
    cmd_args = parts[1] if len(parts) > 1 else ""

    cmd_registry = state.extras.get("command_registry")
    model_registry = state.extras.get("model_registry")

    if cmd_registry is None:
        await state.broadcast({
            "type": "command_response",
            "command": cmd_name,
            "output": "No command registry available.",
        })
        return

    command = cmd_registry.get(cmd_name)
    if command is None:
        available = [c.name for c in cmd_registry.all()]
        output = f"Unknown command: /{cmd_name}\nAvailable: {', '.join('/' + n for n in sorted(available))}"
        await state.broadcast({
            "type": "command_response",
            "command": cmd_name,
            "output": output,
        })
        return

    # Build CommandContext with all available extras
    context = build_command_context(state.agent, **state.extras)

    try:
        result = await command.execute(cmd_args, context)
        output = result or f"/{cmd_name} executed."
    except Exception as exc:
        logger.error("Command /%s error: %s", cmd_name, exc)
        output = f"Error executing /{cmd_name}: {exc}"

    await state.broadcast({
        "type": "command_response",
        "command": cmd_name,
        "output": output,
    })

    # If model command switched, also broadcast model_changed for UI sync
    if cmd_name == "model" and cmd_args.strip() and cmd_args.strip() != "list":
        if model_registry:
            try:
                profiles = model_registry.list_profiles()
                for p in profiles:
                    if p["active"]:
                        await state.broadcast({
                            "type": "model_changed",
                            "key": p["key"],
                            "model_id": p["model_id"],
                            "provider": p["provider"],
                            "base_url": p["base_url"],
                        })
                        break
            except Exception:
                pass


async def _run_agent_message(state: WebUIState, text: str) -> None:
    try:
        await state.agent.handle_user_message(text)
    except asyncio.CancelledError:
        state.agent.turn_runtime.fail("Interrupted by user.")
        await state.bus.emit(Error(message="Interrupted by user."))
        await state.bus.emit(AgentEnd())
    except Exception as exc:
        logger.error("Agent error: %s", exc)
        # Extract user-friendly error from API error responses
        error_msg = str(exc)
        if "429" in error_msg:
            error_msg = "Rate limited — the model provider is temporarily unavailable. Try again shortly or switch to another model with /model."
        elif "401" in error_msg or "403" in error_msg:
            error_msg = "Authentication failed — check your API key configuration."
        elif "timeout" in error_msg.lower():
            error_msg = "Request timed out — the model provider may be slow. Try again."
        state.agent.turn_runtime.fail(error_msg)
        await state.bus.emit(Error(message=error_msg))
        await state.bus.emit(AgentEnd())
    finally:
        current_task = asyncio.current_task()
        if state.current_task is current_task:
            state.current_task = None


def _get_messages(state: WebUIState) -> list[dict[str, Any]]:
    return [
        {
            "role": m.role,
            "content": m.content,
            "tool_calls": m.tool_calls,
            "tool_call_id": m.tool_call_id,
            "name": m.name,
            "reasoning_details": m.reasoning_details,
        }
        for m in state.agent.messages
    ]


def _get_tools_list(state: WebUIState) -> list[dict[str, Any]]:
    return state.agent.registry.list_tools()


def _get_token_usage(state: WebUIState) -> dict[str, Any]:
    runtime = state.agent.turn_runtime.to_dict()
    max_tokens = state.agent.compactor.max_tokens if state.agent.compactor else 128000
    return {
        "message_count": runtime["message_count"],
        "estimated_tokens": runtime["estimated_tokens"],
        "max_tokens": max_tokens,
        "compaction_count": runtime["compaction_count"],
        "context_metrics": runtime["prompt_context_metrics"],
        "provider_usage": runtime["provider_usage"],
    }


def _get_runtime_state(state: WebUIState) -> dict[str, Any]:
    runtime = state.agent.turn_runtime.to_dict()
    extension_runtime = state.extras.get("extension_runtime")
    if extension_runtime is not None:
        runtime["extensions"] = extension_runtime.list_extensions()
    else:
        runtime["extensions"] = []
    return runtime
