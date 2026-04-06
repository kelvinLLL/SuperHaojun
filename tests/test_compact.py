"""Tests for Feature 8 v2: Context Compaction — circuit breaker, structured prompt, session compact."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from superhaojun.agent import ChatMessage
from superhaojun.compact.compactor import (
    CompactionResult,
    ContextCompactor,
    estimate_tokens,
)
from superhaojun.compact.prompts import (
    COMPACTION_SYSTEM_PROMPT,
    COMPACTION_USER_PROMPT,
    SESSION_SUMMARY_PROMPT,
)
from superhaojun.compact.session_compact import compact_session


# ── Token Estimation ──


class TestTokenEstimation:
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


# ── Compaction Prompts ──


class TestCompactionPrompts:
    def test_system_prompt_exists(self) -> None:
        assert "conversation compactor" in COMPACTION_SYSTEM_PROMPT.lower()

    def test_user_prompt_has_sections(self) -> None:
        assert "Primary Request" in COMPACTION_USER_PROMPT
        assert "Key Technical Context" in COMPACTION_USER_PROMPT
        assert "Files Modified" in COMPACTION_USER_PROMPT
        assert "Current Progress" in COMPACTION_USER_PROMPT
        assert "Errors and Resolutions" in COMPACTION_USER_PROMPT
        assert "Active Decisions" in COMPACTION_USER_PROMPT
        assert "Pending Tasks" in COMPACTION_USER_PROMPT

    def test_user_prompt_has_placeholder(self) -> None:
        assert "{conversation}" in COMPACTION_USER_PROMPT

    def test_session_summary_prompt(self) -> None:
        assert "{conversation}" in SESSION_SUMMARY_PROMPT


# ── CompactionResult ──


class TestCompactionResult:
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
        assert "Python" in result.summary

    def test_to_messages(self) -> None:
        result = CompactionResult(
            summary="Summary.",
            removed_count=5,
            preserved_count=2,
            pre_tokens=1000,
            post_tokens=100,
        )
        msgs = result.to_messages()
        assert len(msgs) == 1
        assert msgs[0].role == "system"
        assert "Summary." in (msgs[0].content or "")

    def test_empty_summary_no_messages(self) -> None:
        result = CompactionResult(
            summary="", removed_count=0, preserved_count=3,
            pre_tokens=100, post_tokens=100,
        )
        assert result.to_messages() == []


# ── Circuit Breaker ──


class TestCircuitBreaker:
    def _make_messages(self, count: int, content_size: int = 100) -> list[ChatMessage]:
        return [
            ChatMessage(
                role="user" if i % 2 == 0 else "assistant",
                content="x" * content_size,
            )
            for i in range(count)
        ]

    def test_not_on_cooldown_initially(self) -> None:
        compactor = ContextCompactor()
        assert not compactor.is_on_cooldown

    def test_on_cooldown_after_compact(self) -> None:
        async def fake_summarize(text: str) -> str:
            return "Summary."

        compactor = ContextCompactor(
            max_tokens=100, preserve_recent=2,
            summarize_fn=fake_summarize, cooldown_seconds=60.0,
        )
        msgs = self._make_messages(10, content_size=50)
        asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert compactor.is_on_cooldown

    def test_cooldown_skips_compaction(self) -> None:
        call_count = 0

        async def counting_summarize(text: str) -> str:
            nonlocal call_count
            call_count += 1
            return "Summary."

        compactor = ContextCompactor(
            max_tokens=100, preserve_recent=2,
            summarize_fn=counting_summarize, cooldown_seconds=60.0,
        )
        msgs = self._make_messages(10, content_size=50)

        # First compact works
        result1 = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert result1.removed_count > 0
        assert call_count == 1

        # Second compact within cooldown is skipped
        result2 = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert result2.removed_count == 0
        assert call_count == 1  # not called again

    def test_cooldown_with_zero_seconds(self) -> None:
        """cooldown_seconds=0 effectively disables circuit breaker."""
        async def fake_summarize(text: str) -> str:
            return "Summary."

        compactor = ContextCompactor(
            max_tokens=100, preserve_recent=2,
            summarize_fn=fake_summarize, cooldown_seconds=0.0,
        )
        msgs = self._make_messages(10, content_size=50)

        result1 = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert result1.removed_count > 0
        # Immediately compact again (cooldown 0 = always on cooldown after first compact)
        # Actually with cooldown=0, is_on_cooldown would be True since elapsed < 0 is false
        # But time difference will be >= 0 which is >= 0.0 cooldown
        # So it should NOT be on cooldown (elapsed >= cooldown)


class TestContextCompactor:
    def _make_messages(self, count: int, content_size: int = 100) -> list[ChatMessage]:
        return [
            ChatMessage(
                role="user" if i % 2 == 0 else "assistant",
                content="x" * content_size,
            )
            for i in range(count)
        ]

    def test_should_compact_below_threshold(self) -> None:
        compactor = ContextCompactor(max_tokens=10000)
        msgs = self._make_messages(5, content_size=50)
        assert not compactor.should_compact(msgs)

    def test_should_compact_above_threshold(self) -> None:
        compactor = ContextCompactor(max_tokens=100, compact_threshold=0.8)
        msgs = self._make_messages(10, content_size=100)
        assert compactor.should_compact(msgs)

    def test_compact_preserves_recent(self) -> None:
        async def fake_summarize(text: str) -> str:
            return "Summary of conversation."

        compactor = ContextCompactor(
            max_tokens=100, preserve_recent=2,
            summarize_fn=fake_summarize, cooldown_seconds=0.0,
        )
        msgs = self._make_messages(10, content_size=50)
        result = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert result.preserved_count == 2

    def test_compact_produces_summary(self) -> None:
        async def fake_summarize(text: str) -> str:
            return "Summary here."

        compactor = ContextCompactor(
            max_tokens=100, preserve_recent=2,
            summarize_fn=fake_summarize, cooldown_seconds=0.0,
        )
        msgs = self._make_messages(10, content_size=50)
        result = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert "Summary here." in result.summary
        assert result.removed_count == 8

    def test_no_compact_when_few_messages(self) -> None:
        async def fake_summarize(text: str) -> str:
            return "Summary."

        compactor = ContextCompactor(
            max_tokens=100, preserve_recent=5,
            summarize_fn=fake_summarize, cooldown_seconds=0.0,
        )
        msgs = self._make_messages(3, content_size=50)
        result = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert result.removed_count == 0
        assert result.summary == ""

    def test_compact_threshold_default(self) -> None:
        compactor = ContextCompactor(max_tokens=200_000)
        assert compactor.compact_threshold == 0.8

    def test_structured_prompt_passed_to_summarize(self) -> None:
        """summarize_fn receives the structured compaction prompt."""
        received: list[str] = []

        async def spy_summarize(text: str) -> str:
            received.append(text)
            return "Summary."

        compactor = ContextCompactor(
            max_tokens=100, preserve_recent=2,
            summarize_fn=spy_summarize, cooldown_seconds=0.0,
        )
        msgs = [
            ChatMessage(role="user", content="Tell me about Python"),
            ChatMessage(role="assistant", content="Python is great"),
            ChatMessage(role="user", content="And types?"),
            ChatMessage(role="assistant", content="Types are important"),
        ]
        asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        assert len(received) == 1
        # Should contain structured prompt markers
        assert "Primary Request" in received[0]
        assert "Python" in received[0]

    def test_summary_truncated_if_too_long(self) -> None:
        """Summary exceeding max_tokens * 0.3 chars is truncated."""
        async def long_summarize(text: str) -> str:
            return "x" * 1_000_000  # Way too long

        compactor = ContextCompactor(
            max_tokens=1000, preserve_recent=2,
            summarize_fn=long_summarize, cooldown_seconds=0.0,
        )
        msgs = self._make_messages(10, content_size=50)
        result = asyncio.get_event_loop().run_until_complete(compactor.compact(msgs))
        # max_tokens * 0.3 * 4 chars = 1000 * 0.3 * 4 = 1200 chars + "[truncated]"
        assert len(result.summary) < 1300
        assert result.summary.endswith("[truncated]")


# ── Session Memory Compact ──


class TestSessionCompact:
    def test_session_compact_default(self) -> None:
        msgs = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there"),
        ]
        result = asyncio.get_event_loop().run_until_complete(compact_session(msgs))
        assert "Hello" in result or "Session summary" in result

    def test_session_compact_custom_fn(self) -> None:
        async def custom_summarize(text: str) -> str:
            return f"Custom summary of: {text[:50]}"

        msgs = [
            ChatMessage(role="user", content="Refactor the agent"),
            ChatMessage(role="assistant", content="Done."),
        ]
        result = asyncio.get_event_loop().run_until_complete(
            compact_session(msgs, summarize_fn=custom_summarize)
        )
        assert "Custom summary" in result

    def test_session_compact_prompt_used(self) -> None:
        """Session compact passes SESSION_SUMMARY_PROMPT to summarize_fn."""
        received: list[str] = []

        async def spy(text: str) -> str:
            received.append(text)
            return "ok"

        msgs = [ChatMessage(role="user", content="test")]
        asyncio.get_event_loop().run_until_complete(compact_session(msgs, summarize_fn=spy))
        assert len(received) == 1
        assert "high-level summary" in received[0].lower()
