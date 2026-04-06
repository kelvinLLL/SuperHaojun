"""Tool base class — all tools inherit from this ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """All tools inherit from this ABC. Subclasses implement name/description/parameters/execute."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name passed to openai function calling (a-z, 0-9, _, -)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description — helps LLM decide when to use it."""

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return result as string."""

    @property
    def is_concurrent_safe(self) -> bool:
        """Whether this tool can run in parallel with others. Default True (read-only)."""
        return True

    @property
    def risk_level(self) -> str:
        """Risk level for future permission system: "read" | "write" | "dangerous"."""
        return "read"

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to openai SDK tool definition format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
