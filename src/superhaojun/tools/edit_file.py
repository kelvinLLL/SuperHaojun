"""EditFile tool — precise string replacement in a file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool


class EditFileTool(Tool):
    """Replace an exact string in a file with new content."""

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Replace an exact string occurrence in a file. "
            "The old_string must match exactly (including whitespace and indentation). "
            "Provide enough context lines to uniquely identify the target."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement string",
                },
            },
            "required": ["path", "old_string", "new_string"],
        }

    @property
    def is_concurrent_safe(self) -> bool:
        return False

    @property
    def risk_level(self) -> str:
        return "write"

    async def execute(self, **kwargs: Any) -> str:
        path_str = kwargs.get("path", "")
        old_string = kwargs.get("old_string", "")
        new_string = kwargs.get("new_string", "")

        if not path_str:
            return "Error: path parameter is required"
        if not old_string:
            return "Error: old_string parameter is required"

        p = Path(path_str)
        try:
            content = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"Error: file not found: {path_str}"
        except PermissionError:
            return f"Error: permission denied: {path_str}"

        count = content.count(old_string)
        if count == 0:
            return f"Error: old_string not found in {path_str}"
        if count > 1:
            return f"Error: old_string found {count} times in {path_str}. Provide more context to uniquely identify."

        new_content = content.replace(old_string, new_string, 1)
        try:
            p.write_text(new_content, encoding="utf-8")
        except PermissionError:
            return f"Error: permission denied: {path_str}"
        except Exception as exc:
            return f"Error writing file: {exc}"

        return f"Successfully edited {path_str}"
