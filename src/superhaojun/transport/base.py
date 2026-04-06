"""Transport ABC — abstract message delivery layer.

Transports handle raw message delivery across boundaries.
Routing and deduplication are handled by MessageBus.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Transport(ABC):
    """Abstract transport for sending/receiving messages across boundaries.

    Implementations:
    - LocalTransport: in-process via asyncio.Queue
    - (future) WebSocketTransport, StdioTransport, SSETransport
    """

    @abstractmethod
    async def send(self, message: Any) -> None:
        """Send a message to the other end."""

    @abstractmethod
    async def receive(self) -> Any:
        """Receive the next message. Blocks until available."""

    @abstractmethod
    async def close(self) -> None:
        """Close the transport and release resources."""
