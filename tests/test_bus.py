"""Tests for MessageBus and BoundedUUIDSet."""

from __future__ import annotations

import asyncio

import pytest

from superhaojun.bus import BoundedUUIDSet, MessageBus
from superhaojun.messages import (
    AgentEnd, PermissionRequest, PermissionResponse, TextDelta,
)


class TestBoundedUUIDSet:
    def test_add_and_has(self) -> None:
        s = BoundedUUIDSet(10)
        s.add("abc")
        assert s.has("abc")
        assert not s.has("xyz")

    def test_eviction(self) -> None:
        s = BoundedUUIDSet(3)
        s.add("a")
        s.add("b")
        s.add("c")
        assert s.has("a")
        s.add("d")  # evicts "a"
        assert not s.has("a")
        assert s.has("d")

    def test_duplicate_add(self) -> None:
        s = BoundedUUIDSet(3)
        s.add("a")
        s.add("a")
        assert len(s) == 1

    def test_clear(self) -> None:
        s = BoundedUUIDSet(10)
        s.add("a")
        s.add("b")
        s.clear()
        assert not s.has("a")
        assert len(s) == 0

    def test_full_cycle(self) -> None:
        s = BoundedUUIDSet(3)
        for i in range(10):
            s.add(str(i))
        assert len(s) == 3
        # Only last 3 remain
        assert s.has("7")
        assert s.has("8")
        assert s.has("9")
        assert not s.has("0")


class TestMessageBus:
    async def test_emit_dispatches_to_handler(self) -> None:
        bus = MessageBus()
        received: list = []
        bus.on("text_delta", lambda m: received.append(m))
        msg = TextDelta(text="hello")
        await bus.emit(msg)
        assert len(received) == 1
        assert received[0].text == "hello"

    async def test_emit_dedup(self) -> None:
        bus = MessageBus()
        received: list = []
        bus.on("text_delta", lambda m: received.append(m))
        msg = TextDelta(text="hello", id="fixed-id")
        await bus.emit(msg)
        await bus.emit(msg)  # same id → dedup
        assert len(received) == 1

    async def test_multiple_handlers(self) -> None:
        bus = MessageBus()
        a: list = []
        b: list = []
        bus.on("text_delta", lambda m: a.append(m))
        bus.on("text_delta", lambda m: b.append(m))
        await bus.emit(TextDelta(text="x"))
        assert len(a) == 1
        assert len(b) == 1

    async def test_off_removes_handler(self) -> None:
        bus = MessageBus()
        received: list = []
        handler = lambda m: received.append(m)
        bus.on("text_delta", handler)
        bus.off("text_delta", handler)
        await bus.emit(TextDelta(text="x"))
        assert len(received) == 0

    async def test_wait_for(self) -> None:
        bus = MessageBus()

        async def delayed_emit():
            await asyncio.sleep(0.01)
            await bus.emit(PermissionResponse(tool_call_id="c1", granted=True))

        asyncio.create_task(delayed_emit())
        response = await bus.wait_for("permission_response", match_id="c1")
        assert response.granted is True

    async def test_expect_then_emit(self) -> None:
        bus = MessageBus()
        future = bus.expect("permission_response", match_id="c1")
        await bus.emit(PermissionResponse(tool_call_id="c1", granted=False))
        response = await future
        assert response.granted is False

    async def test_type_only_wait(self) -> None:
        bus = MessageBus()
        future = bus.expect("agent_end")
        await bus.emit(AgentEnd())
        result = await future
        assert result.TYPE == "agent_end"

    async def test_async_handler_runs_as_task(self) -> None:
        bus = MessageBus()
        received: list = []

        async def async_handler(msg: TextDelta) -> None:
            await asyncio.sleep(0.01)
            received.append(msg)

        bus.on("text_delta", async_handler)
        await bus.emit(TextDelta(text="hello"))
        # Handler was scheduled as task, not awaited inline
        assert len(received) == 0
        await asyncio.sleep(0.02)
        assert len(received) == 1

    async def test_seen_count(self) -> None:
        bus = MessageBus()
        await bus.emit(TextDelta(text="a"))
        await bus.emit(TextDelta(text="b"))
        assert bus.seen_count == 2

    async def test_permission_request_response_flow(self) -> None:
        """Full permission flow: expect → emit request → handler responds → future resolves."""
        bus = MessageBus()

        async def auto_grant(msg: PermissionRequest) -> None:
            await bus.emit(PermissionResponse(
                tool_call_id=msg.tool_call_id, granted=True,
            ))

        bus.on("permission_request", auto_grant)

        future = bus.expect("permission_response", match_id="c1")
        await bus.emit(PermissionRequest(
            tool_call_id="c1", tool_name="bash",
            arguments={"cmd": "ls"}, risk_level="dangerous",
        ))
        # auto_grant is async → task → need to yield
        await asyncio.sleep(0.01)
        response = await future
        assert response.granted is True
