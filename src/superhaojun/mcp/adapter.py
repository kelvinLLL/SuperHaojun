"""MCPToolAdapter — wraps an MCP server tool as a local Tool ABC instance.

This allows MCP tools to be registered in the ToolRegistry alongside
built-in tools, providing unified tool scheduling.
"""

from __future__ import annotations

from typing import Any

from ..tools.base import Tool
from .client import MCPClient


class MCPToolAdapter(Tool):
    """Adapts an MCP server tool to the local Tool ABC interface.

    Attributes:
        _client: The MCP client connection to the server.
        _name: Tool name from the MCP server (prefixed with server name).
        _description: Tool description from the server.
        _input_schema: JSON Schema for tool parameters.
        _server_name: Name of the MCP server providing this tool.
    """

    def __init__(
        self,
        client: MCPClient,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        server_name: str,
    ) -> None:
        self._client = client
        self._tool_name = tool_name
        self._description = description
        self._input_schema = input_schema
        self._server_name = server_name

    @property
    def name(self) -> str:
        """Prefixed name: mcp__{server}__{tool} to avoid collisions."""
        return f"mcp__{self._server_name}__{self._tool_name}"

    @property
    def description(self) -> str:
        return f"[MCP:{self._server_name}] {self._description}"

    @property
    def parameters(self) -> dict[str, Any]:
        return self._input_schema if self._input_schema else {
            "type": "object",
            "properties": {},
        }

    @property
    def is_concurrent_safe(self) -> bool:
        # MCP tools are external; assume concurrent safe by default
        return True

    @property
    def risk_level(self) -> str:
        # MCP tools are external; default to "write" for safety
        return "write"

    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool by calling the MCP server."""
        try:
            return await self._client.call_tool(self._tool_name, kwargs)
        except Exception as exc:
            return f"MCP tool error ({self._server_name}/{self._tool_name}): {exc}"
