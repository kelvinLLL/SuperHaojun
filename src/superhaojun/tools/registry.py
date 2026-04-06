"""ToolRegistry — manages registered tools and provides lookup / batch conversion."""

from __future__ import annotations

from typing import Any

from .base import Tool


class ToolRegistry:
    """Manages registered tools, provides lookup and batch conversion to openai format."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [t.to_openai_tool() for t in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)
