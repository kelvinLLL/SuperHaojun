"""Tests for Feature 9: Session Persistence."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from superhaojun.agent import ChatMessage
from superhaojun.session.manager import SessionInfo, SessionManager


class TestSessionManager:
    """Core CRUD operations on sessions."""

    def test_create_session(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        session = mgr.create("test-session")
        assert session.name == "test-session"
        assert session.session_id
        assert session.created_at > 0

    def test_create_generates_unique_ids(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        s1 = mgr.create("a")
        s2 = mgr.create("b")
        assert s1.session_id != s2.session_id

    def test_list_empty(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        assert mgr.list_sessions() == []

    def test_list_after_save(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        messages = [ChatMessage(role="user", content="hello")]
        mgr.save("s1", messages)
        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].name == "s1"

    def test_save_and_load(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        messages = [
            ChatMessage(role="user", content="hello"),
            ChatMessage(role="assistant", content="hi there"),
        ]
        mgr.save("chat1", messages)
        loaded = mgr.load("chat1")
        assert len(loaded) == 2
        assert loaded[0].role == "user"
        assert loaded[0].content == "hello"
        assert loaded[1].role == "assistant"

    def test_save_overwrites(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        mgr.save("s1", [ChatMessage(role="user", content="v1")])
        mgr.save("s1", [ChatMessage(role="user", content="v2")])
        loaded = mgr.load("s1")
        assert len(loaded) == 1
        assert loaded[0].content == "v2"

    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        assert mgr.load("nonexistent") == []

    def test_delete(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        mgr.save("s1", [ChatMessage(role="user", content="hello")])
        assert mgr.delete("s1") is True
        assert mgr.load("s1") == []

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        assert mgr.delete("nope") is False

    def test_storage_dir_created(self, tmp_path: Path) -> None:
        storage = tmp_path / "sessions"
        mgr = SessionManager(storage_dir=storage)
        mgr.save("test", [ChatMessage(role="user", content="x")])
        assert storage.exists()


class TestSessionSerialization:
    """Messages with tool_calls and tool results serialize correctly."""

    def test_tool_call_roundtrip(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        messages = [
            ChatMessage(
                role="assistant",
                content=None,
                tool_calls=[{
                    "id": "tc_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "x.py"}'},
                }],
            ),
            ChatMessage(
                role="tool",
                content="file content here",
                tool_call_id="tc_1",
                name="read_file",
            ),
        ]
        mgr.save("tool-test", messages)
        loaded = mgr.load("tool-test")
        assert loaded[0].tool_calls is not None
        assert loaded[0].tool_calls[0]["id"] == "tc_1"
        assert loaded[1].role == "tool"
        assert loaded[1].tool_call_id == "tc_1"


class TestSessionInfo:
    """SessionInfo metadata."""

    def test_fields(self) -> None:
        now = time.time()
        info = SessionInfo(
            session_id="abc123",
            name="test",
            created_at=now,
            message_count=5,
        )
        assert info.session_id == "abc123"
        assert info.name == "test"
        assert info.message_count == 5


class TestSessionListOrdering:
    """Sessions listed in reverse chronological order."""

    def test_most_recent_first(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        mgr.save("old", [ChatMessage(role="user", content="old")])
        mgr.save("new", [ChatMessage(role="user", content="new")])
        sessions = mgr.list_sessions()
        assert len(sessions) == 2
        # Most recently saved should be first
        assert sessions[0].name == "new"
