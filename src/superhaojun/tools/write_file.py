"""WriteFile tool — create or overwrite a file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool


class WriteFileTool(Tool):
    """Create or overwrite a file with the given content."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Create or overwrite a file at the given path with the provided content."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path to write",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file",
                },
            },
            "required": ["path", "content"],
        }

    @property
    def is_concurrent_safe(self) -> bool:
        return False

    @property
    def risk_level(self) -> str:
        return "write"

    async def execute(self, **kwargs: Any) -> str:
        path_str = kwargs.get("path", "")
        content = kwargs.get("content", "")
        if not path_str:
            return "Error: path parameter is required"

        p = Path(path_str)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except PermissionError:
            return f"Error: permission denied: {path_str}"
        except Exception as exc:
            return f"Error writing file: {exc}"

        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"Successfully wrote {lines} lines to {path_str}"
