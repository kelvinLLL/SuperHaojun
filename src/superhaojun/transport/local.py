"""LocalTransport — in-process message transport using asyncio.Queue.

Use create_pair() to get two linked transports for bidirectional communication.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .base import Transport


class LocalTransport(Transport):
    """In-process transport backed by asyncio.Queue.

    A's outbound is B's inbound and vice versa.
    """

    def __init__(self, inbound: asyncio.Queue[Any], outbound: asyncio.Queue[Any]) -> None:
        self._inbound = inbound
        self._outbound = outbound

    async def send(self, message: Any) -> None:
        await self._outbound.put(message)

    async def receive(self) -> Any:
        return await self._inbound.get()

    async def close(self) -> None:
        pass

    @staticmethod
    def create_pair() -> tuple[LocalTransport, LocalTransport]:
        """Create two linked transports."""
        q1: asyncio.Queue[Any] = asyncio.Queue()
        q2: asyncio.Queue[Any] = asyncio.Queue()
        return LocalTransport(q1, q2), LocalTransport(q2, q1)
