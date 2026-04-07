"""MCP server configuration v2 — multi-scope config loading.

v2 changes:
- Multi-scope: ~/.haojun/mcp.json (user) + .haojun/mcp.json (project)
- Project scope overrides user scope (by name)
- MCPServerConfig gains status tracking fields
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class MCPServerStatus(StrEnum):
    """Runtime status of an MCP server connection."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for a single MCP server connection."""
    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    enabled: bool = True
    scope: str = "project"  # "user" or "project"


def _load_scope(path: Path, scope: str) -> list[MCPServerConfig]:
    """Load configs from a single scope file."""
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
            scope=scope,
        ))
    return configs


def load_mcp_configs(
    project_path: Path | None = None,
    user_path: Path | None = None,
) -> list[MCPServerConfig]:
    """Load and merge MCP configs from user + project scopes.

    Project configs override user configs when names collide.
    """
    user_configs = _load_scope(user_path, "user") if user_path else []
    project_configs = _load_scope(project_path, "project") if project_path else []

    # Merge: project wins
    by_name: dict[str, MCPServerConfig] = {}
    for cfg in user_configs:
        by_name[cfg.name] = cfg
    for cfg in project_configs:
        by_name[cfg.name] = cfg
    return list(by_name.values())
