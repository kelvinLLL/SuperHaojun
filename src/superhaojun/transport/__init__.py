"""Transport package — experimental message delivery helpers.

The transport abstraction is intentionally not a first-class runtime assembly
boundary yet. It stays available for focused tests and future cross-boundary
work, but callers should treat it as experimental until a real entrypoint
depends on it.
"""

from .base import Transport
from .local import LocalTransport

EXPERIMENTAL = True

__all__ = ["EXPERIMENTAL", "Transport", "LocalTransport"]
