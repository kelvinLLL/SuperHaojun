"""Glob tool — file pattern search."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool

MAX_RESULTS = 500


class GlobTool(Tool):
    """Search for files matching a glob pattern."""

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return (
            "Search for files matching a glob pattern. "
            "Supports ** for recursive matching. Returns file paths, one per line."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. '**/*.py', 'src/**/*.ts')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search from (default: current directory)",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, **kwargs: Any) -> str:
        pattern = kwargs.get("pattern", "")
        base_path = kwargs.get("path", ".")

        if not pattern:
            return "Error: pattern parameter is required"

        base = Path(base_path)
        if not base.is_dir():
            return f"Error: directory not found: {base_path}"

        try:
            matches = sorted(str(p) for p in base.glob(pattern) if p.is_file())
        except Exception as exc:
            return f"Error: invalid glob pattern: {exc}"

        if not matches:
            return f"No files matching '{pattern}' in {base_path}"

        if len(matches) > MAX_RESULTS:
            return "\n".join(matches[:MAX_RESULTS]) + f"\n... ({len(matches) - MAX_RESULTS} more files)"

        return "\n".join(matches)
