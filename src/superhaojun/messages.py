"""Message protocol — structured, serializable messages with type discrimination.

Each message is a frozen dataclass with:
- TYPE (ClassVar[str]): discriminator for routing and serialization
- id (str): unique UUID for deduplication
- timestamp (float): creation time (epoch seconds)

Replaces events.py. Messages are transport-ready and can cross process boundaries.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, fields as dc_fields
from typing import Any, ClassVar
from uuid import uuid4


# ── Message type registry ──

_REGISTRY: dict[str, type] = {}


def _register(cls: type) -> type:
    _REGISTRY[cls.TYPE] = cls
    return cls


def message_to_dict(msg: Any) -> dict[str, Any]:
    """Serialize a message to a dict with 'type' discriminator."""
    d: dict[str, Any] = {"type": msg.TYPE}
    for f in dc_fields(msg):
        val = getattr(msg, f.name)
        if isinstance(val, BaseException):
            d[f.name] = str(val)
        else:
            d[f.name] = val
    return d


def message_from_dict(data: dict[str, Any]) -> Any:
    """Deserialize a message from a dict using 'type' discriminator."""
    data = dict(data)
    type_key = data.pop("type")
    cls = _REGISTRY.get(type_key)
    if cls is None:
        raise ValueError(f"Unknown message type: {type_key}")
    valid = {f.name for f in dc_fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid}
    return cls(**filtered)


# ── Outbound: Agent → Consumer ──


@_register
@dataclass(frozen=True)
class TextDelta:
    """A chunk of streamed LLM text output."""
    TYPE: ClassVar[str] = "text_delta"
    text: str
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@_register
@dataclass(frozen=True)
class ToolCallStart:
    """Tool execution is about to begin."""
    TYPE: ClassVar[str] = "tool_call_start"
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@_register
@dataclass(frozen=True)
class ToolCallEnd:
    """Tool execution completed."""
    TYPE: ClassVar[str] = "tool_call_end"
    tool_call_id: str
    tool_name: str
    result: str
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@_register
@dataclass(frozen=True)
class PermissionRequest:
    """Agent requests permission before executing a tool."""
    TYPE: ClassVar[str] = "permission_request"
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    risk_level: str
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@_register
@dataclass(frozen=True)
class TurnStart:
    """A new LLM API call is starting."""
    TYPE: ClassVar[str] = "turn_start"
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@_register
@dataclass(frozen=True)
class TurnEnd:
    """An LLM API call finished."""
    TYPE: ClassVar[str] = "turn_end"
    finish_reason: str = "stop"
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@_register
@dataclass(frozen=True)
class AgentStart:
    """Agent begins processing a user message."""
    TYPE: ClassVar[str] = "agent_start"
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@_register
@dataclass(frozen=True)
class AgentEnd:
    """Agent finished processing."""
    TYPE: ClassVar[str] = "agent_end"
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@_register
@dataclass(frozen=True)
class Error:
    """An error occurred during agent processing."""
    TYPE: ClassVar[str] = "error"
    message: str
    exception: BaseException | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


# ── Inbound: Consumer → Agent ──


@_register
@dataclass(frozen=True)
class UserMessage:
    """User sends a message to the agent."""
    TYPE: ClassVar[str] = "user_message"
    text: str
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@_register
@dataclass(frozen=True)
class PermissionResponse:
    """User's permission decision."""
    TYPE: ClassVar[str] = "permission_response"
    tool_call_id: str
    granted: bool
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@_register
@dataclass(frozen=True)
class Interrupt:
    """Interrupt the agent's current operation."""
    TYPE: ClassVar[str] = "interrupt"
    reason: str = ""
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)


# ── Union types ──

OutboundMessage = (
    TextDelta | ToolCallStart | ToolCallEnd | PermissionRequest
    | TurnStart | TurnEnd | AgentStart | AgentEnd | Error
)

InboundMessage = UserMessage | PermissionResponse | Interrupt

Message = OutboundMessage | InboundMessage
