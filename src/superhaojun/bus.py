"""MessageBus — message routing, deduplication, and request-response coordination.

Corresponds to Claude Code's Bridge role:
- Routes messages by TYPE to registered handlers
- Deduplicates via BoundedUUIDSet (ring buffer, O(1) lookup)
- Supports request-response via expect() / wait_for()
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class BoundedUUIDSet:
    """O(1) membership check with bounded memory.

    Uses a ring buffer to evict oldest entries when capacity is reached.
    Mirrors Claude Code's BoundedUUIDSet for echo filtering + re-delivery defense.
    """

    def __init__(self, capacity: int = 2000) -> None:
        self._capacity = capacity
        self._ring: list[str | None] = [None] * capacity
        self._set: set[str] = set()
        self._write_idx = 0

    def add(self, uuid: str) -> None:
        if uuid in self._set:
            return
        evicted = self._ring[self._write_idx]
        if evicted is not None:
            self._set.discard(evicted)
        self._ring[self._write_idx] = uuid
        self._set.add(uuid)
        self._write_idx = (self._write_idx + 1) % self._capacity

    def has(self, uuid: str) -> bool:
        return uuid in self._set

    def clear(self) -> None:
        self._set.clear()
        self._ring = [None] * self._capacity
        self._write_idx = 0

    def __len__(self) -> int:
        return len(self._set)


class MessageBus:
    """Central message dispatcher with deduplication and request-response support.

    - emit(): dedup → resolve waiters → dispatch to handlers
    - on() / off(): register / remove handlers for a message type
    - expect(): set up a Future resolved when a matching message arrives
    - wait_for(): convenience for expect() + await

    Async handlers are spawned as tasks (non-blocking), enabling flows like
    permission request-response where the handler prompts the user while
    the agent awaits a Future.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}
        self._waiters: dict[tuple[str, str], asyncio.Future] = {}
        self._seen = BoundedUUIDSet(2000)

    async def emit(self, message: Any) -> None:
        """Emit a message: dedup → resolve waiters → dispatch to handlers."""
        msg_id = message.id
        if self._seen.has(msg_id):
            return
        self._seen.add(msg_id)

        self._resolve_waiters(message)

        type_key = message.TYPE
        for handler in list(self._handlers.get(type_key, [])):
            result = handler(message)
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)

    def on(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a message type."""
        self._handlers.setdefault(message_type, []).append(handler)

    def off(self, message_type: str, handler: Callable) -> None:
        """Remove a handler."""
        handlers = self._handlers.get(message_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def expect(self, message_type: str, match_id: str = "") -> asyncio.Future:
        """Set up a waiter. Returns a Future (don't await yet).

        If match_id is provided, it matches against the message's tool_call_id.
        Call this BEFORE emitting the corresponding request message.
        """
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        key = (message_type, match_id)
        self._waiters[key] = future
        return future

    async def wait_for(self, message_type: str, match_id: str = "") -> Any:
        """Wait for a message of the given type. Convenience for expect + await."""
        return await self.expect(message_type, match_id)

    def _resolve_waiters(self, message: Any) -> bool:
        """Try to resolve pending waiters. Returns True if any resolved."""
        type_key = message.TYPE
        match_id = getattr(message, "tool_call_id", "")
        resolved = False

        # Exact match (type + tool_call_id)
        if match_id:
            key = (type_key, match_id)
            if key in self._waiters:
                self._waiters.pop(key).set_result(message)
                resolved = True

        # Type-only match
        key = (type_key, "")
        if key in self._waiters:
            self._waiters.pop(key).set_result(message)
            resolved = True

        return resolved

    @property
    def seen_count(self) -> int:
        return len(self._seen)
