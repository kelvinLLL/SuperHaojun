"""Tests for transport layer."""

from __future__ import annotations

import pytest

from superhaojun.transport import LocalTransport
from superhaojun.messages import TextDelta


class TestLocalTransport:
    async def test_create_pair(self) -> None:
        a, b = LocalTransport.create_pair()
        msg = TextDelta(text="hello")
        await a.send(msg)
        received = await b.receive()
        assert received.text == "hello"

    async def test_bidirectional(self) -> None:
        a, b = LocalTransport.create_pair()
        await a.send(TextDelta(text="from_a"))
        await b.send(TextDelta(text="from_b"))
        assert (await b.receive()).text == "from_a"
        assert (await a.receive()).text == "from_b"

    async def test_close(self) -> None:
        a, b = LocalTransport.create_pair()
        await a.close()
        await b.close()
