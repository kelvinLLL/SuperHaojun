"""MCP server configuration — defines how to connect to MCP servers.

Configuration is loaded from .haojun/mcp.json:
```json
{
  "servers": [
    {
      "name": "filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": {}
    },
    {
      "name": "web-search",
      "transport": "sse",
      "url": "http://localhost:3001/sse"
    }
  ]
}
```
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for a single MCP server connection.

    Attributes:
        name: Human-readable server identifier.
        transport: Connection type — "stdio" or "sse".
        command: For stdio transport, the command to spawn.
        args: Command arguments for stdio transport.
        env: Additional environment variables for the subprocess.
        url: For SSE transport, the server URL.
        enabled: Whether this server is active.
    """
    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    enabled: bool = True


def load_mcp_configs(path: Path) -> list[MCPServerConfig]:
    """Load MCP server configurations from JSON file.

    Returns empty list if file missing or invalid.
    """
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    configs: list[MCPServerConfig] = []
    for item in data.get("servers", []):
        if not isinstance(item, dict) or "name" not in item:
            continue
        configs.append(MCPServerConfig(
            name=item["name"],
            transport=item.get("transport", "stdio"),
            command=item.get("command", ""),
            args=item.get("args", []),
            env=item.get("env", {}),
            url=item.get("url", ""),
            enabled=item.get("enabled", True),
        ))
    return configs
