"""ListDir tool — list directory contents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool


class ListDirTool(Tool):
    """List the contents of a directory."""

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List files and directories in the given path. Directories end with /."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list (default: current directory)",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        path_str = kwargs.get("path", ".")

        p = Path(path_str)
        if not p.exists():
            return f"Error: path not found: {path_str}"
        if not p.is_dir():
            return f"Error: not a directory: {path_str}"

        try:
            entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return f"Error: permission denied: {path_str}"

        if not entries:
            return "(empty directory)"

        lines: list[str] = []
        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")

        return "\n".join(lines)
