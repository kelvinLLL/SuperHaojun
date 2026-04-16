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
from .config import MCPServerApproval, MCPServerConfig, MCPServerStatus

logger = logging.getLogger(__name__)


@dataclass
class MCPServerState:
    """Runtime state for one MCP server."""
    config: MCPServerConfig
    approval: MCPServerApproval = MCPServerApproval.PENDING
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
                self._servers[cfg.name] = MCPServerState(
                    config=cfg,
                    approval=cfg.effective_approval,
                    status=status,
                )

    async def start_all(self) -> None:
        """Start all enabled servers."""
        for name, state in self._servers.items():
            if state.config.enabled and state.status == MCPServerStatus.STOPPED:
                if not self._can_start(state):
                    continue
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
        if not self._can_start(state):
            return False
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
        if not self._can_start(state):
            return False
        await self._stop_server(name)
        state.status = MCPServerStatus.STOPPED
        await self._start_server(name)
        return state.status == MCPServerStatus.RUNNING

    async def approve(self, name: str) -> bool:
        """Mark a server as approved without implicitly starting it."""
        return await self.set_approval(name, MCPServerApproval.APPROVED)

    async def deny(self, name: str) -> bool:
        """Mark a server as denied and stop it if it is running."""
        return await self.set_approval(name, MCPServerApproval.DENIED)

    async def set_approval(self, name: str, approval: MCPServerApproval) -> bool:
        """Update a server approval state and keep the config object in sync."""
        state = self._servers.get(name)
        if not state:
            return False
        was_disabled = state.status == MCPServerStatus.DISABLED
        if approval != MCPServerApproval.APPROVED and state.client is not None:
            await self._stop_server(name)

        state.approval = approval
        state.config = state.config.with_approval(approval)

        if approval == MCPServerApproval.APPROVED:
            if state.error in {
                "Approval required before startup.",
                "Server approval denied.",
            }:
                state.error = ""
            if state.status != MCPServerStatus.DISABLED and state.client is None:
                state.status = MCPServerStatus.STOPPED
        elif approval == MCPServerApproval.PENDING:
            state.error = "Approval required before startup."
            state.status = MCPServerStatus.DISABLED if was_disabled else MCPServerStatus.STOPPED
        else:
            state.error = "Server approval denied."
            state.status = MCPServerStatus.DISABLED if was_disabled else MCPServerStatus.STOPPED
        return True

    def get_status(self) -> list[dict[str, str]]:
        """Get status of all servers (for /mcp list and WebUI)."""
        return [
            {
                "name": name,
                "status": state.status.value,
                "approval": state.approval.value,
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

    def _can_start(self, state: MCPServerState) -> bool:
        if state.approval == MCPServerApproval.APPROVED:
            state.error = ""
            return True
        if state.approval == MCPServerApproval.DENIED:
            state.error = "Server approval denied."
            return False
        state.error = "Approval required before startup."
        return False

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
