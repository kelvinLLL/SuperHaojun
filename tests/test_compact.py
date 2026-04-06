"""Tests for Feature 8: Context Compaction."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from superhaojun.agent import ChatMessage
from superhaojun.compact.compactor import (
    CompactionResult,
    ContextCompactor,
    estimate_tokens,
)


class TestTokenEstimation:
    """Rough token counting: ~4 chars per token."""

    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_short_string(self) -> None:
        result = estimate_tokens("hello world")
        assert 2 <= result <= 5

    def test_proportional(self) -> None:
        short = estimate_tokens("hello")
        long = estimate_tokens("hello " * 100)
        assert long > short * 10

    def test_messages_list(self) -> None:
        msgs = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there, how can I help?"),
        ]
        total = sum(estimate_tokens(m.content or "") for m in msgs)
        assert total > 0


class TestCompactionResult:
    """CompactionResult dataclass."""

    def test_fields(self) -> None:
        result = CompactionResult(
            summary="Conversation about Python.",
            removed_count=10,
            preserved_count=2,
            pre_tokens=5000,
            post_tokens=500,
        )
        assert result.removed_count == 10
        assert result.preserved_count == 2
        assert result.pre_tokens == 5000
        assert result.post_tokens == 500
        assert "Python" in result.summary


class TestContextCompactor:
    """Compaction logic — threshold detection and message replacement."""

    def _make_messages(self, count: int, content_size: int = 100) -> list[ChatMessage]:
        msgs = []
        for i in range(count):
            role = "user" if i % 2 == 0 else "assistant"
            msgs.append(ChatMessage(role=role, content="x" * content_size))
        return msgs

    def test_should_compact_below_threshold(self) -> None:
        compactor = ContextCompactor(max_tokens=10000)
        msgs = self._make_messages(5, content_size=50)
        assert not compactor.should_compact(msgs)

    def test_should_compact_above_threshold(self) -> None:
        compactor = ContextCompactor(max_tokens=100, compact_threshold=0.8)
        msgs = self._make_messages(10, content_size=100)
        assert compactor.should_compact(msgs)

    def test_compact_preserves_recent(self) -> None:
        """After compaction, most recent messages are preserved."""
        async def fake_summarize(text: str) -> str:
            return "Summary of conversation."

        compactor = ContextCompactor(
            max_tokens=100,
            preserve_recent=2,
            summarize_fn=fake_summarize,
        )
        msgs = self._make_messages(10, content_size=50)
        result = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert result.preserved_count == 2  # last 2 messages kept

    def test_compact_produces_summary_message(self) -> None:
        async def fake_summarize(text: str) -> str:
            return "Summary here."

        compactor = ContextCompactor(
            max_tokens=100,
            preserve_recent=2,
            summarize_fn=fake_summarize,
        )
        msgs = self._make_messages(10, content_size=50)
        result = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert "Summary here." in result.summary
        assert result.removed_count == 8  # 10 - 2 preserved

    def test_compact_returns_new_messages(self) -> None:
        async def fake_summarize(text: str) -> str:
            return "Summarized."

        compactor = ContextCompactor(
            max_tokens=100,
            preserve_recent=3,
            summarize_fn=fake_summarize,
        )
        msgs = self._make_messages(10, content_size=50)
        result = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        new_msgs = result.to_messages()
        # to_messages returns summary boundary only; caller appends preserved
        assert new_msgs[0].role == "system"
        assert "Summarized." in (new_msgs[0].content or "")
        assert len(new_msgs) == 1  # summary boundary message only

    def test_no_compact_when_few_messages(self) -> None:
        async def fake_summarize(text: str) -> str:
            return "Summary."

        compactor = ContextCompactor(
            max_tokens=100,
            preserve_recent=5,
            summarize_fn=fake_summarize,
        )
        msgs = self._make_messages(3, content_size=50)
        result = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        # Nothing to remove when messages count <= preserve_recent
        assert result.removed_count == 0
        assert result.summary == ""

    def test_token_estimation_in_should_compact(self) -> None:
        """Threshold is fraction of max_tokens."""
        compactor = ContextCompactor(max_tokens=1000, compact_threshold=0.5)
        # ~25 tokens per message (100 chars / 4)
        msgs = self._make_messages(25, content_size=100)
        # 25 * 25 = 625 tokens > 500 (0.5 * 1000)
        assert compactor.should_compact(msgs)

    def test_compact_threshold_default(self) -> None:
        compactor = ContextCompactor(max_tokens=200_000)
        assert compactor.compact_threshold == 0.8


class TestCompactIntegration:
    """Integration with summarize_fn pattern."""

    def test_summarize_fn_receives_conversation_text(self) -> None:
        received: list[str] = []

        async def spy_summarize(text: str) -> str:
            received.append(text)
            return "Summary."

        compactor = ContextCompactor(
            max_tokens=100,
            preserve_recent=2,
            summarize_fn=spy_summarize,
        )
        msgs = [
            ChatMessage(role="user", content="Tell me about Python"),
            ChatMessage(role="assistant", content="Python is a language"),
            ChatMessage(role="user", content="What about types?"),
            ChatMessage(role="assistant", content="Types are important"),
        ]
        asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert len(received) == 1
        assert "Python" in received[0]
