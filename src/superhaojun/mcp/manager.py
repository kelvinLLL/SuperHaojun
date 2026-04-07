"""MCPManager v2 — unified lifecycle, enable/disable/reconnect at runtime.

v2 changes:
- Central manager with per-server status tracking
- Runtime enable/disable/reconnect API
- Auto-register/unregister tools in ToolRegistry
- Status exposure for WebUI/commands
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .adapter import MCPToolAdapter
from .client import MCPClient, MCPToolInfo
from .config import MCPServerConfig, MCPServerStatus

logger = logging.getLogger(__name__)


@dataclass
class MCPServerState:
    """Runtime state for one MCP server."""
    config: MCPServerConfig
    status: MCPServerStatus = MCPServerStatus.STOPPED
    client: MCPClient | None = None
    tools: list[MCPToolInfo] = field(default_factory=list)
    error: str = ""


@dataclass
class MCPManager:
    """Unified MCP server lifecycle manager.

    Manages multiple MCP server connections from config.
    Provides enable/disable/reconnect at runtime.
    Registers discovered tools into a ToolRegistry.
    """
    _servers: dict[str, MCPServerState] = field(default_factory=dict)
    _tool_registry: Any | None = None  # ToolRegistry, optional

    def set_tool_registry(self, registry: Any) -> None:
        self._tool_registry = registry

    def load_configs(self, configs: list[MCPServerConfig]) -> None:
        """Load server configs. Replaces existing unstarted configs."""
        for cfg in configs:
            if cfg.name not in self._servers:
                status = MCPServerStatus.DISABLED if not cfg.enabled else MCPServerStatus.STOPPED
                self._servers[cfg.name] = MCPServerState(config=cfg, status=status)

    async def start_all(self) -> None:
        """Start all enabled servers."""
        for name, state in self._servers.items():
            if state.config.enabled and state.status == MCPServerStatus.STOPPED:
                await self._start_server(name)

    async def stop_all(self) -> None:
        """Stop all running servers."""
        for name in list(self._servers):
            await self._stop_server(name)

    async def enable(self, name: str) -> bool:
        """Enable and start a server."""
        state = self._servers.get(name)
        if not state:
            return False
        if state.status == MCPServerStatus.RUNNING:
            return True
        state.status = MCPServerStatus.STOPPED
        await self._start_server(name)
        return state.status == MCPServerStatus.RUNNING

    async def disable(self, name: str) -> bool:
        """Stop and disable a server."""
        state = self._servers.get(name)
        if not state:
            return False
        await self._stop_server(name)
        state.status = MCPServerStatus.DISABLED
        return True

    async def reconnect(self, name: str) -> bool:
        """Restart a server connection."""
        state = self._servers.get(name)
        if not state:
            return False
        await self._stop_server(name)
        state.status = MCPServerStatus.STOPPED
        await self._start_server(name)
        return state.status == MCPServerStatus.RUNNING

    def get_status(self) -> list[dict[str, str]]:
        """Get status of all servers (for /mcp list and WebUI)."""
        return [
            {
                "name": name,
                "status": state.status.value,
                "transport": state.config.transport,
                "tools_count": str(len(state.tools)),
                "error": state.error,
                "scope": state.config.scope,
            }
            for name, state in self._servers.items()
        ]

    def get_server_tools(self, name: str) -> list[MCPToolInfo]:
        """Get tools from a specific server."""
        state = self._servers.get(name)
        return state.tools if state else []

    def list_all_tools(self) -> list[MCPToolInfo]:
        """List tools from all running servers."""
        tools: list[MCPToolInfo] = []
        for state in self._servers.values():
            if state.status == MCPServerStatus.RUNNING:
                tools.extend(state.tools)
        return tools

    # --- Internal ---

    async def _start_server(self, name: str) -> None:
        state = self._servers[name]
        state.status = MCPServerStatus.STARTING
        state.error = ""
        client = MCPClient(config=state.config)
        try:
            await client.start()
            tools = await client.list_tools()
            state.client = client
            state.tools = tools
            state.status = MCPServerStatus.RUNNING
            logger.info("MCP server '%s' started with %d tools", name, len(tools))
            self._register_tools(state)
        except Exception as exc:
            state.status = MCPServerStatus.ERROR
            state.error = str(exc)
            logger.warning("MCP server '%s' failed to start: %s", name, exc)
            try:
                await client.stop()
            except Exception:
                pass

    async def _stop_server(self, name: str) -> None:
        state = self._servers.get(name)
        if not state or not state.client:
            return
        self._unregister_tools(state)
        try:
            await state.client.stop()
        except Exception as exc:
            logger.warning("Error stopping MCP server '%s': %s", name, exc)
        state.client = None
        state.tools = []
        state.status = MCPServerStatus.STOPPED

    def _register_tools(self, state: MCPServerState) -> None:
        if not self._tool_registry or not state.client:
            return
        for tool_info in state.tools:
            adapter = MCPToolAdapter(
                client=state.client,
                tool_name=tool_info.name,
                description=tool_info.description,
                input_schema=tool_info.input_schema,
                server_name=state.config.name,
            )
            self._tool_registry.register(adapter)

    def _unregister_tools(self, state: MCPServerState) -> None:
        if not self._tool_registry:
            return
        for tool_info in state.tools:
            tool_name = f"mcp__{state.config.name}__{tool_info.name}"
            self._tool_registry.unregister(tool_name)
