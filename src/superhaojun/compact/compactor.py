"""ContextCompactor — detects token threshold and compresses conversation.

Strategy (inspired by Claude Code's services/compact/):
1. estimate_tokens(): rough estimation (~4 chars per token)
2. should_compact(): check if total context exceeds threshold fraction of max
3. compact(): fork an LLM call (via summarize_fn) to produce summary,
   replace old messages with summary + preserved recent messages
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import ChatMessage


def estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 characters per token."""
    return len(text) // 4


def _messages_token_count(messages: list[ChatMessage]) -> int:
    total = 0
    for m in messages:
        total += estimate_tokens(m.content or "")
        if m.tool_calls:
            total += estimate_tokens(str(m.tool_calls))
    return total


def _messages_to_text(messages: list[ChatMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        prefix = m.role.upper()
        lines.append(f"[{prefix}]: {m.content or ''}")
    return "\n".join(lines)


@dataclass(frozen=True)
class CompactionResult:
    """Result of a compaction operation."""
    summary: str
    removed_count: int
    preserved_count: int
    pre_tokens: int
    post_tokens: int

    def to_messages(self) -> list[ChatMessage]:
        """Build replacement message list: summary boundary + preserved messages.

        Caller should have preserved messages stored separately.
        This returns just the summary as a system message.
        """
        from ..agent import ChatMessage
        result: list[ChatMessage] = []
        if self.summary:
            result.append(ChatMessage(
                role="system",
                content=f"[Conversation compacted]\n{self.summary}",
            ))
        return result


# Default no-op summarize function (real one calls LLM)
async def _default_summarize(text: str) -> str:
    return f"Previous conversation summary:\n{text[:500]}"


@dataclass
class ContextCompactor:
    """Manages context compaction for a conversation.

    Args:
        max_tokens: Model's context window size.
        compact_threshold: Fraction of max_tokens that triggers compaction (default 0.8).
        preserve_recent: Number of recent messages to keep after compaction.
        summarize_fn: Async callable that takes conversation text and returns summary.
    """
    max_tokens: int = 200_000
    compact_threshold: float = 0.8
    preserve_recent: int = 4
    summarize_fn: Callable[[str], Awaitable[str]] = _default_summarize

    def should_compact(self, messages: list[ChatMessage]) -> bool:
        """Check if conversation exceeds compaction threshold."""
        token_count = _messages_token_count(messages)
        return token_count >= self.max_tokens * self.compact_threshold

    async def compact(self, messages: list[ChatMessage]) -> CompactionResult:
        """Compact the conversation: summarize old messages, preserve recent ones.

        Returns CompactionResult with summary and metadata.
        The caller is responsible for replacing agent.messages.
        """
        pre_tokens = _messages_token_count(messages)

        # Nothing to compact if messages fit within preserve window
        if len(messages) <= self.preserve_recent:
            return CompactionResult(
                summary="",
                removed_count=0,
                preserved_count=len(messages),
                pre_tokens=pre_tokens,
                post_tokens=pre_tokens,
            )

        # Split: old messages to summarize, recent to preserve
        split_idx = len(messages) - self.preserve_recent
        old_messages = messages[:split_idx]
        preserved = messages[split_idx:]

        # Build text for summarization
        conversation_text = _messages_to_text(old_messages)
        summary = await self.summarize_fn(conversation_text)

        # Calculate post-compaction tokens
        summary_result = CompactionResult(
            summary=summary,
            removed_count=len(old_messages),
            preserved_count=len(preserved),
            pre_tokens=pre_tokens,
            post_tokens=estimate_tokens(summary) + _messages_token_count(preserved),
        )

        return summary_result
