"""Explicit per-turn runtime state for explainable agent execution."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .compact.compactor import estimate_tokens
from .tool_orchestration import ToolCallInfo

if TYPE_CHECKING:
    from .conversation import ChatMessage


@dataclass
class TurnRuntimeState:
    """Mutable snapshot of the current or most recent LLM turn."""

    turn_index: int = 0
    phase: str = "idle"
    model_id: str = ""
    finish_reason: str | None = None
    text_chunks: list[str] = field(default_factory=list)
    reasoning_chunks: list[str] = field(default_factory=list)
    buffered_tool_calls: list[dict[str, str]] = field(default_factory=list)
    tool_statuses: list[dict[str, str | None]] = field(default_factory=list)
    message_count: int = 0
    estimated_tokens: int = 0
    current_turn_text_tokens: int = 0
    current_turn_reasoning_tokens: int = 0
    compaction_pending: bool = False
    compaction_count: int = 0
    last_compaction: dict[str, int] | None = None
    memory_entry: dict[str, Any] | None = None
    active: bool = False
    started_at: float | None = None
    ended_at: float | None = None
    last_error: str | None = None

    def start_turn(self, *, model_id: str) -> None:
        self.turn_index += 1
        self.phase = "streaming"
        self.model_id = model_id
        self.finish_reason = None
        self.text_chunks.clear()
        self.reasoning_chunks.clear()
        self.buffered_tool_calls.clear()
        self.tool_statuses.clear()
        self.current_turn_text_tokens = 0
        self.current_turn_reasoning_tokens = 0
        self.memory_entry = None
        self.active = True
        self.started_at = time.time()
        self.ended_at = None
        self.last_error = None

    def record_text_delta(self, text: str) -> None:
        self.text_chunks.append(text)
        self.current_turn_text_tokens += estimate_tokens(text)

    def record_reasoning_delta(self, text: str) -> None:
        self.reasoning_chunks.append(text)
        self.current_turn_reasoning_tokens += estimate_tokens(text)

    def set_buffered_tool_calls(self, tool_calls: list[ToolCallInfo]) -> None:
        self.buffered_tool_calls = [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            }
            for tool_call in tool_calls
        ]

    def set_tool_queue(self, tool_calls: list[ToolCallInfo]) -> None:
        self.tool_statuses = [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
                "status": "pending",
                "detail": None,
            }
            for tool_call in tool_calls
        ]

    def mark_tool_status(
        self,
        tool_call: ToolCallInfo,
        status: str,
        detail: str | None = None,
    ) -> None:
        for entry in self.tool_statuses:
            if entry["id"] == tool_call.id:
                entry["status"] = status
                entry["detail"] = detail
                break
        else:
            self.tool_statuses.append(
                {
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                    "status": status,
                    "detail": detail,
                }
            )

    def update_message_metrics(
        self,
        messages: list[ChatMessage],
        *,
        compaction_pending: bool,
    ) -> None:
        self.message_count = len(messages)
        total = 0
        for message in messages:
            total += estimate_tokens(message.content or "")
            if message.tool_calls:
                total += estimate_tokens(str(message.tool_calls))
        self.estimated_tokens = total
        self.compaction_pending = compaction_pending

    def record_compaction(
        self,
        *,
        removed_count: int,
        preserved_count: int,
        pre_tokens: int,
        post_tokens: int,
        message_count: int,
    ) -> None:
        self.compaction_count += 1
        self.last_compaction = {
            "removed_count": removed_count,
            "preserved_count": preserved_count,
            "pre_tokens": pre_tokens,
            "post_tokens": post_tokens,
        }
        self.message_count = message_count
        self.estimated_tokens = post_tokens
        self.compaction_pending = False

    def set_memory_entry(self, metadata: dict[str, Any] | None) -> None:
        self.memory_entry = None if metadata is None else {
            key: [dict(item) for item in value] if key == "loaded_entries" else value
            for key, value in metadata.items()
        }

    def enter_tool_phase(self, *, finish_reason: str | None) -> None:
        self.phase = "tool_execution"
        self.finish_reason = finish_reason

    def complete(self, *, finish_reason: str | None) -> None:
        self.phase = "completed"
        self.finish_reason = finish_reason
        self.active = False
        self.ended_at = time.time()

    def fail(self, message: str) -> None:
        self.phase = "error"
        self.last_error = message
        self.active = False
        self.ended_at = time.time()

    def reset(self) -> None:
        self.phase = "idle"
        self.model_id = ""
        self.finish_reason = None
        self.text_chunks.clear()
        self.reasoning_chunks.clear()
        self.buffered_tool_calls.clear()
        self.tool_statuses.clear()
        self.message_count = 0
        self.estimated_tokens = 0
        self.current_turn_text_tokens = 0
        self.current_turn_reasoning_tokens = 0
        self.compaction_pending = False
        self.compaction_count = 0
        self.last_compaction = None
        self.memory_entry = None
        self.active = False
        self.started_at = None
        self.ended_at = None
        self.last_error = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "phase": self.phase,
            "model_id": self.model_id,
            "finish_reason": self.finish_reason,
            "text_chunks": list(self.text_chunks),
            "reasoning_chunks": list(self.reasoning_chunks),
            "buffered_tool_calls": list(self.buffered_tool_calls),
            "tool_statuses": [dict(entry) for entry in self.tool_statuses],
            "message_count": self.message_count,
            "estimated_tokens": self.estimated_tokens,
            "current_turn_text_tokens": self.current_turn_text_tokens,
            "current_turn_reasoning_tokens": self.current_turn_reasoning_tokens,
            "compaction_pending": self.compaction_pending,
            "compaction_count": self.compaction_count,
            "last_compaction": dict(self.last_compaction) if self.last_compaction else None,
            "memory_entry": (
                {
                    key: [dict(item) for item in value] if key == "loaded_entries" else value
                    for key, value in self.memory_entry.items()
                }
                if self.memory_entry else None
            ),
            "active": self.active,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "last_error": self.last_error,
        }
