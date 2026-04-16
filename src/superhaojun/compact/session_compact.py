"""Session Memory Compact — generate session-level summaries.

Produces a structured summary when a session ends or is manually compacted.
The summary can be:
- Stored as session metadata
- Used for context injection when resuming
- Fed into auto-extraction for cross-session memory (Feature 10)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from .prompts import SESSION_SUMMARY_PROMPT

if TYPE_CHECKING:
    from ..conversation import ChatMessage


def _messages_to_text(messages: list[ChatMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        prefix = m.role.upper()
        lines.append(f"[{prefix}]: {m.content or ''}")
    return "\n".join(lines)


async def _default_session_summarize(text: str) -> str:
    """Fallback: truncate to 1000 chars."""
    return f"Session summary:\n{text[:1000]}"


async def compact_session(
    messages: list[ChatMessage],
    summarize_fn: Callable[[str], Awaitable[str]] | None = None,
) -> str:
    """Generate a session-level summary from the full conversation.

    Args:
        messages: Full conversation history.
        summarize_fn: Async function that takes conversation text and returns summary.
                      If None, uses default truncation.

    Returns:
        Session summary string.
    """
    fn = summarize_fn or _default_session_summarize
    conversation_text = _messages_to_text(messages)
    prompt = SESSION_SUMMARY_PROMPT.format(conversation=conversation_text)
    return await fn(prompt)
