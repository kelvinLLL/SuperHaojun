"""ContextCompactor v2 — sub-agent based compaction with circuit breaker.

Key improvements over v1:
- Structured compaction prompt (7-section format from prompts.py)
- Circuit breaker: cooldown between compactions to prevent infinite loops
- Token output limit: compaction summary capped at max_tokens * 0.3
- Sub-agent pattern: compaction uses separate LLM call (via summarize_fn)
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .prompts import COMPACTION_USER_PROMPT

if TYPE_CHECKING:
    from ..conversation import ChatMessage


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
        """Build replacement message list: summary boundary message.

        Caller appends preserved messages after this.
        """
        from ..conversation import ChatMessage
        result: list[ChatMessage] = []
        if self.summary:
            result.append(ChatMessage(
                role="system",
                content=f"[Conversation compacted]\n{self.summary}",
            ))
        return result


async def _default_summarize(text: str) -> str:
    """Default summarize: use structured prompt, truncate result."""
    return f"Previous conversation summary:\n{text[:500]}"


@dataclass
class ContextCompactor:
    """Manages context compaction with circuit breaker protection.

    Args:
        max_tokens: Model's context window size.
        compact_threshold: Fraction of max_tokens that triggers compaction.
        preserve_recent: Number of recent messages to keep after compaction.
        summarize_fn: Async callable for LLM-based summarization.
        cooldown_seconds: Minimum seconds between compactions (circuit breaker).
    """
    max_tokens: int = 200_000
    compact_threshold: float = 0.8
    preserve_recent: int = 4
    summarize_fn: Callable[[str], Awaitable[str]] = _default_summarize
    cooldown_seconds: float = 30.0
    _last_compact_time: float = field(default=0.0, repr=False)

    def should_compact(self, messages: list[ChatMessage]) -> bool:
        """Check if conversation exceeds compaction threshold."""
        token_count = _messages_token_count(messages)
        return token_count >= self.max_tokens * self.compact_threshold

    @property
    def is_on_cooldown(self) -> bool:
        """True if circuit breaker is active (compacted too recently)."""
        if self._last_compact_time == 0.0:
            return False
        return (time.monotonic() - self._last_compact_time) < self.cooldown_seconds

    async def compact(self, messages: list[ChatMessage]) -> CompactionResult:
        """Compact the conversation using structured prompt.

        Returns CompactionResult with summary and metadata.
        The caller is responsible for replacing agent.messages.
        """
        pre_tokens = _messages_token_count(messages)

        # Circuit breaker check
        if self.is_on_cooldown:
            return CompactionResult(
                summary="",
                removed_count=0,
                preserved_count=len(messages),
                pre_tokens=pre_tokens,
                post_tokens=pre_tokens,
            )

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

        # Build structured prompt for summarization
        conversation_text = _messages_to_text(old_messages)
        prompt_text = COMPACTION_USER_PROMPT.format(conversation=conversation_text)

        # Call summarize_fn (sub-agent LLM call in production)
        summary = await self.summarize_fn(prompt_text)

        # Enforce token output limit: max_tokens * 0.3
        max_summary_tokens = int(self.max_tokens * 0.3)
        max_summary_chars = max_summary_tokens * 4
        if len(summary) > max_summary_chars:
            summary = summary[:max_summary_chars] + "\n[truncated]"

        # Update circuit breaker timestamp
        object.__setattr__(self, '_last_compact_time', time.monotonic())

        return CompactionResult(
            summary=summary,
            removed_count=len(old_messages),
            preserved_count=len(preserved),
            pre_tokens=pre_tokens,
            post_tokens=estimate_tokens(summary) + _messages_token_count(preserved),
        )
