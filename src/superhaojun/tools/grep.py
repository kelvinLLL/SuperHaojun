"""Grep tool — search file contents by regex or text."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Tool

MAX_RESULTS = 200


class GrepTool(Tool):
    """Search for text or regex pattern in files."""

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return (
            "Search file contents for a text or regex pattern. "
            "Returns matching lines with file paths and line numbers."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Search pattern (regex supported)",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in (default: current directory)",
                },
                "glob": {
                    "type": "string",
                    "description": "File glob filter (e.g. '*.py'). Only used when path is a directory.",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, **kwargs: Any) -> str:
        pattern = kwargs.get("pattern", "")
        search_path = kwargs.get("path", ".")
        file_glob = kwargs.get("glob", "**/*")

        if not pattern:
            return "Error: pattern parameter is required"

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            return f"Error: invalid regex pattern: {exc}"

        p = Path(search_path)
        if not p.exists():
            return f"Error: path not found: {search_path}"

        files: list[Path] = []
        if p.is_file():
            files = [p]
        elif p.is_dir():
            files = sorted(f for f in p.glob(file_glob) if f.is_file())

        matches: list[str] = []
        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except (PermissionError, OSError):
                continue

            for i, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{f}:{i}: {line.rstrip()}")
                    if len(matches) >= MAX_RESULTS:
                        matches.append(f"... (truncated at {MAX_RESULTS} results)")
                        return "\n".join(matches)

        if not matches:
            return f"No matches for '{pattern}' in {search_path}"

        return "\n".join(matches)
