"""Tests for message protocol."""

from __future__ import annotations

import pytest

from superhaojun.messages import (
    AgentEnd, AgentStart, Error, Interrupt,
    PermissionRequest, PermissionResponse,
    TextDelta, ToolCallEnd, ToolCallStart,
    TurnEnd, TurnStart, UserMessage,
    message_from_dict, message_to_dict,
)


class TestMessageCreation:
    def test_text_delta(self) -> None:
        m = TextDelta(text="hello")
        assert m.text == "hello"
        assert m.TYPE == "text_delta"
        assert len(m.id) == 32
        assert m.timestamp > 0

    def test_tool_call_start(self) -> None:
        m = ToolCallStart(tool_call_id="c1", tool_name="read_file", arguments={"path": "a.txt"})
        assert m.TYPE == "tool_call_start"
        assert m.tool_name == "read_file"
        assert m.arguments == {"path": "a.txt"}

    def test_tool_call_end(self) -> None:
        m = ToolCallEnd(tool_call_id="c1", tool_name="read_file", result="contents")
        assert m.TYPE == "tool_call_end"
        assert m.result == "contents"

    def test_permission_request(self) -> None:
        m = PermissionRequest(
            tool_call_id="c1", tool_name="bash",
            arguments={"cmd": "ls"}, risk_level="dangerous",
        )
        assert m.TYPE == "permission_request"
        assert m.risk_level == "dangerous"

    def test_permission_response(self) -> None:
        m = PermissionResponse(tool_call_id="c1", granted=True)
        assert m.TYPE == "permission_response"
        assert m.granted is True

    def test_turn_start_end(self) -> None:
        assert TurnStart().TYPE == "turn_start"
        m = TurnEnd(finish_reason="tool_calls")
        assert m.finish_reason == "tool_calls"

    def test_agent_start_end(self) -> None:
        assert AgentStart().TYPE == "agent_start"
        assert AgentEnd().TYPE == "agent_end"

    def test_error(self) -> None:
        exc = ValueError("boom")
        m = Error(message="failed", exception=exc)
        assert m.message == "failed"
        assert m.exception is exc

    def test_user_message(self) -> None:
        m = UserMessage(text="hello")
        assert m.TYPE == "user_message"
        assert m.text == "hello"

    def test_interrupt(self) -> None:
        m = Interrupt(reason="user cancelled")
        assert m.TYPE == "interrupt"
        assert m.reason == "user cancelled"

    def test_messages_are_frozen(self) -> None:
        m = TextDelta(text="x")
        with pytest.raises(AttributeError):
            m.text = "y"  # type: ignore[misc]

    def test_unique_ids(self) -> None:
        m1 = TextDelta(text="a")
        m2 = TextDelta(text="b")
        assert m1.id != m2.id


class TestSerialization:
    def test_to_dict(self) -> None:
        m = TextDelta(text="hello", id="abc123", timestamp=1000.0)
        d = message_to_dict(m)
        assert d["type"] == "text_delta"
        assert d["text"] == "hello"
        assert d["id"] == "abc123"
        assert d["timestamp"] == 1000.0

    def test_from_dict(self) -> None:
        d = {"type": "text_delta", "text": "hello", "id": "abc123", "timestamp": 1000.0}
        m = message_from_dict(d)
        assert isinstance(m, TextDelta)
        assert m.text == "hello"
        assert m.id == "abc123"

    def test_roundtrip(self) -> None:
        original = ToolCallStart(
            tool_call_id="c1", tool_name="bash", arguments={"cmd": "ls"},
        )
        d = message_to_dict(original)
        restored = message_from_dict(d)
        assert restored.tool_call_id == original.tool_call_id
        assert restored.tool_name == original.tool_name
        assert restored.arguments == original.arguments
        assert restored.id == original.id

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown message type"):
            message_from_dict({"type": "nonexistent"})

    def test_error_with_exception_serializes(self) -> None:
        m = Error(message="boom", exception=ValueError("details"))
        d = message_to_dict(m)
        assert d["type"] == "error"
        assert d["exception"] == "details"

    def test_inbound_roundtrip(self) -> None:
        original = PermissionResponse(tool_call_id="c1", granted=False)
        d = message_to_dict(original)
        restored = message_from_dict(d)
        assert isinstance(restored, PermissionResponse)
        assert restored.tool_call_id == "c1"
        assert restored.granted is False
