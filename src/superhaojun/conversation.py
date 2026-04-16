"""Shared conversation and transcript models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    """A single message in the conversation history."""

    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    reasoning_details: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "reasoning_details": self.reasoning_details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatMessage:
        return cls(
            role=data["role"],
            content=data.get("content"),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
            reasoning_details=data.get("reasoning_details"),
        )


@dataclass
class ConversationState:
    """Lightweight owner of the in-memory transcript."""

    messages: list[ChatMessage] = field(default_factory=list)

    def append(self, message: ChatMessage) -> None:
        self.messages.append(message)

    def extend(self, messages: list[ChatMessage]) -> None:
        self.messages.extend(messages)

    def clear(self) -> None:
        self.messages.clear()
