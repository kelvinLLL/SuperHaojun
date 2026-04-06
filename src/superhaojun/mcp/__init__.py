"""MCP package — Model Context Protocol client integration.

Connects to external MCP servers, wraps their tools as Tool ABC instances,
and registers them into the shared ToolRegistry for unified scheduling.
"""

from .adapter import MCPToolAdapter
from .client import MCPClient
from .config import MCPServerConfig

__all__ = ["MCPClient", "MCPServerConfig", "MCPToolAdapter"]
