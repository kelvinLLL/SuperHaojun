"""ReadFile tool — reads file contents with line numbers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool


class ReadFileTool(Tool):
    """Read the contents of a file at the given path."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path. Returns file content with line numbers."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path to read",
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        path_str = kwargs.get("path", "")
        if not path_str:
            return "Error: path parameter is required"

        p = Path(path_str)
        try:
            content = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"Error: file not found: {path_str}"
        except PermissionError:
            return f"Error: permission denied: {path_str}"
        except Exception as exc:
            return f"Error reading file: {exc}"

        lines = content.splitlines(keepends=True)
        numbered = [f"{i + 1:4d} | {line}" for i, line in enumerate(lines)]
        return "".join(numbered)
