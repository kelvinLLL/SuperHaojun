"""MCP server configuration v2 — multi-scope config loading.

v2 changes:
- Multi-scope: ~/.haojun/mcp.json (user) + .haojun/mcp.json (project)
- Project scope overrides user scope (by name)
- MCPServerConfig gains status tracking fields
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
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


class MCPServerApproval(StrEnum):
    """Trust state of an MCP server configuration."""

    APPROVED = "approved"
    PENDING = "pending"
    DENIED = "denied"


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
    approval: MCPServerApproval | None = None

    @property
    def effective_approval(self) -> MCPServerApproval:
        if self.approval is not None:
            return self.approval
        if self.scope == "user":
            return MCPServerApproval.APPROVED
        return MCPServerApproval.PENDING

    def with_approval(self, approval: MCPServerApproval | None) -> MCPServerConfig:
        """Return a copy of this config with updated approval metadata."""
        return replace(self, approval=approval)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the config back to the on-disk MCP JSON shape."""
        data: dict[str, Any] = {
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "url": self.url,
            "enabled": self.enabled,
        }
        if self.approval is not None:
            data["approval"] = self.approval.value
        return data


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
        approval = item.get("approval")
        configs.append(MCPServerConfig(
            name=item["name"],
            transport=item.get("transport", "stdio"),
            command=item.get("command", ""),
            args=item.get("args", []),
            env=item.get("env", {}),
            url=item.get("url", ""),
            enabled=item.get("enabled", True),
            scope=scope,
            approval=(
                MCPServerApproval(approval)
                if approval in {value.value for value in MCPServerApproval}
                else None
            ),
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
