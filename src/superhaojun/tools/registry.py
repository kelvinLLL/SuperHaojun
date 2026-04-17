"""ToolRegistry — manages registered tools and provides lookup / batch conversion."""

from __future__ import annotations

from typing import Any

from .base import Tool


class ToolRegistry:
    """Manages registered tools, provides lookup and batch conversion to openai format."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._disabled: set[str] = set()

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        self._disabled.discard(tool.name)

    def unregister(self, name: str) -> bool:
        removed = self._tools.pop(name, None) is not None
        self._disabled.discard(name)
        return removed

    def get(self, name: str) -> Tool | None:
        if name in self._disabled:
            return None
        return self._tools.get(name)

    def get_registered(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def enable(self, name: str) -> bool:
        if name not in self._tools:
            return False
        self._disabled.discard(name)
        return True

    def disable(self, name: str) -> bool:
        if name not in self._tools:
            return False
        self._disabled.add(name)
        return True

    def is_enabled(self, name: str) -> bool:
        return name in self._tools and name not in self._disabled

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "risk_level": tool.risk_level,
                "enabled": tool.name not in self._disabled,
            }
            for tool in self._tools.values()
        ]

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [
            tool.to_openai_tool()
            for name, tool in self._tools.items()
            if name not in self._disabled
        ]

    def __len__(self) -> int:
        return sum(1 for name in self._tools if name not in self._disabled)
