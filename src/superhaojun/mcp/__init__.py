"""MCP package — Model Context Protocol client integration.

Connects to external MCP servers, wraps their tools as Tool ABC instances,
and registers them into the shared ToolRegistry for unified scheduling.
"""

from .adapter import MCPToolAdapter
from .client import MCPClient
from .config import (
    MCPServerApproval,
    MCPServerConfig,
    MCPServerStatus,
    load_mcp_configs,
)
from .manager import MCPManager

__all__ = [
    "MCPClient", "MCPManager", "MCPServerApproval", "MCPServerConfig",
    "MCPServerStatus", "MCPToolAdapter", "load_mcp_configs",
]
