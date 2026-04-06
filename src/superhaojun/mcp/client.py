"""MCP Client — JSON-RPC 2.0 over stdio/SSE to communicate with MCP servers.

Implements the client side of the Model Context Protocol:
- initialize handshake
- tools/list to discover server tools
- tools/call to execute a tool
- Lifecycle management (start/stop subprocess)

Uses bare asyncio subprocess for stdio transport (no external MCP SDK dependency).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from .config import MCPServerConfig

logger = logging.getLogger(__name__)

_JSONRPC_VERSION = "2.0"
_MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass
class MCPToolInfo:
    """Tool metadata discovered from an MCP server."""
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class MCPClient:
    """Client for a single MCP server.

    Lifecycle:
        client = MCPClient(config)
        await client.start()       # spawn process + initialize
        tools = await client.list_tools()
        result = await client.call_tool("name", {"arg": "val"})
        await client.stop()
    """
    config: MCPServerConfig
    _process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    _request_id: int = field(default=0, repr=False)
    _pending: dict[int, asyncio.Future] = field(default_factory=dict, repr=False)
    _reader_task: asyncio.Task | None = field(default=None, repr=False)
    _initialized: bool = field(default=False, repr=False)
    _server_capabilities: dict[str, Any] = field(default_factory=dict, repr=False)

    async def start(self) -> None:
        """Spawn the MCP server subprocess and perform initialization handshake."""
        if self.config.transport != "stdio":
            raise NotImplementedError(f"Transport '{self.config.transport}' not yet supported")

        if not self.config.command:
            raise ValueError(f"MCP server '{self.config.name}' has no command configured")

        env = {**os.environ, **self.config.env}
        self._process = await asyncio.create_subprocess_exec(
            self.config.command, *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        await self._initialize()

    async def stop(self) -> None:
        """Gracefully shut down the MCP server."""
        if self._process and self._process.returncode is None:
            try:
                await self._send_notification("notifications/cancelled", {})
            except Exception:
                pass
            try:
                self._process.stdin.close()  # type: ignore[union-attr]
            except Exception:
                pass
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._process.kill()
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._initialized = False
        self._pending.clear()

    @property
    def is_running(self) -> bool:
        return (
            self._process is not None
            and self._process.returncode is None
            and self._initialized
        )

    async def list_tools(self) -> list[MCPToolInfo]:
        """Request the tool list from the MCP server."""
        result = await self._send_request("tools/list", {})
        tools_raw = result.get("tools", [])
        return [
            MCPToolInfo(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in tools_raw
            if isinstance(t, dict) and "name" in t
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the MCP server and return the text result."""
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        # MCP tool results have "content" array
        content_items = result.get("content", [])
        texts = []
        for item in content_items:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts) if texts else json.dumps(result)

    # --- Internal JSON-RPC ---

    async def _initialize(self) -> None:
        """Send initialize request and initialized notification."""
        result = await self._send_request("initialize", {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "superhaojun", "version": "0.1.0"},
        })
        self._server_capabilities = result.get("capabilities", {})
        await self._send_notification("notifications/initialized", {})
        self._initialized = True
        logger.info("MCP server '%s' initialized", self.config.name)

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response."""
        self._request_id += 1
        req_id = self._request_id
        message = {
            "jsonrpc": _JSONRPC_VERSION,
            "id": req_id,
            "method": method,
            "params": params,
        }
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = future
        self._write(message)
        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"MCP request '{method}' timed out after 30s")

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message = {
            "jsonrpc": _JSONRPC_VERSION,
            "method": method,
            "params": params,
        }
        self._write(message)

    def _write(self, message: dict[str, Any]) -> None:
        """Write a JSON-RPC message to the server's stdin."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("MCP server not running")
        data = json.dumps(message, ensure_ascii=False) + "\n"
        self._process.stdin.write(data.encode("utf-8"))

    async def _read_loop(self) -> None:
        """Read JSON-RPC responses from the server's stdout."""
        if not self._process or not self._process.stdout:
            return
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                req_id = data.get("id")
                if req_id is not None and req_id in self._pending:
                    future = self._pending.pop(req_id)
                    if "error" in data:
                        future.set_exception(
                            RuntimeError(f"MCP error: {data['error']}")
                        )
                    else:
                        future.set_result(data.get("result", {}))
                # Notifications from server are logged but not processed
                elif "method" in data:
                    logger.debug("MCP notification: %s", data.get("method"))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("MCP read loop error: %s", exc)
