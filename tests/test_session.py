"""Tests for Feature 9 v2: Session Persistence — JSONL + backward compat."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from superhaojun.conversation import ChatMessage
from superhaojun.session.manager import SessionInfo, SessionManager, SessionWriter


# ── SessionWriter ──


class TestSessionWriter:
    def test_write_header_and_messages(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        with SessionWriter(path) as writer:
            writer.write_header(SessionInfo(
                session_id="abc", name="test", created_at=1000.0,
            ))
            writer.append(ChatMessage(role="user", content="hello"))
            writer.append(ChatMessage(role="assistant", content="hi"))

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3
        header = json.loads(lines[0])
        assert header["type"] == "header"
        assert header["session_id"] == "abc"
        msg1 = json.loads(lines[1])
        assert msg1["type"] == "message"
        assert msg1["role"] == "user"

    def test_append_flushes_immediately(self, tmp_path: Path) -> None:
        """Each append is flushed — crash-safe."""
        path = tmp_path / "test.jsonl"
        writer = SessionWriter(path)
        writer.write_header(SessionInfo(
            session_id="x", name="t", created_at=0,
        ))
        writer.append(ChatMessage(role="user", content="msg1"))
        # Read file without closing writer
        text = path.read_text(encoding="utf-8")
        assert "msg1" in text
        writer.close()

    def test_context_manager(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        with SessionWriter(path) as w:
            w.write_header(SessionInfo(session_id="x", name="t", created_at=0))
        assert path.exists()

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "test.jsonl"
        with SessionWriter(path) as w:
            w.write_header(SessionInfo(session_id="x", name="t", created_at=0))
        assert path.exists()


# ── SessionManager CRUD ──


class TestSessionManager:
    def test_create_session(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        session = mgr.create("test-session")
        assert session.name == "test-session"
        assert session.session_id
        assert session.created_at > 0

    def test_create_unique_ids(self, tmp_path: Path) -> None:
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

    def test_save_with_session_summary(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        mgr.save("s1", [ChatMessage(role="user", content="hi")],
                 session_summary="Did refactoring work.")
        sessions = mgr.list_sessions()
        assert sessions[0].session_summary == "Did refactoring work."


# ── JSONL Format ──


class TestJSONLFormat:
    def test_file_is_jsonl(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        mgr.save("test", [ChatMessage(role="user", content="hello")])
        path = tmp_path / "test.jsonl"
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2  # header + 1 message
        header = json.loads(lines[0])
        assert header["type"] == "header"

    def test_corrupted_line_skipped(self, tmp_path: Path) -> None:
        """JSONL reader skips corrupted lines."""
        path = tmp_path / "test.jsonl"
        header = {"type": "header", "session_id": "x", "name": "test", "created_at": 0}
        msg = {"type": "message", "role": "user", "content": "ok"}
        path.write_text(
            json.dumps(header) + "\n"
            + "THIS IS CORRUPTED\n"
            + json.dumps(msg) + "\n",
            encoding="utf-8",
        )
        mgr = SessionManager(storage_dir=tmp_path)
        loaded = mgr.load("test")
        assert len(loaded) == 1
        assert loaded[0].content == "ok"


# ── Backward Compatibility ──


class TestBackwardCompatibility:
    def test_reads_legacy_json(self, tmp_path: Path) -> None:
        """Can read old-format .json session files."""
        data = {
            "session_id": "old123",
            "name": "legacy",
            "created_at": 1000.0,
            "message_count": 1,
            "messages": [{"role": "user", "content": "old message"}],
        }
        (tmp_path / "legacy.json").write_text(json.dumps(data), encoding="utf-8")
        mgr = SessionManager(storage_dir=tmp_path)
        loaded = mgr.load("legacy")
        assert len(loaded) == 1
        assert loaded[0].content == "old message"

    def test_legacy_json_in_list(self, tmp_path: Path) -> None:
        data = {
            "session_id": "old123",
            "name": "legacy",
            "created_at": 1000.0,
            "message_count": 2,
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ],
        }
        (tmp_path / "legacy.json").write_text(json.dumps(data), encoding="utf-8")
        mgr = SessionManager(storage_dir=tmp_path)
        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].name == "legacy"

    def test_save_replaces_legacy_with_jsonl(self, tmp_path: Path) -> None:
        """Saving over a legacy JSON creates JSONL and removes old .json."""
        data = {
            "session_id": "old",
            "name": "migrate",
            "created_at": 1000.0,
            "message_count": 1,
            "messages": [{"role": "user", "content": "old"}],
        }
        (tmp_path / "migrate.json").write_text(json.dumps(data), encoding="utf-8")
        mgr = SessionManager(storage_dir=tmp_path)
        mgr.save("migrate", [ChatMessage(role="user", content="new")])
        # Legacy file removed
        assert not (tmp_path / "migrate.json").exists()
        # New JSONL file created
        assert (tmp_path / "migrate.jsonl").exists()
        loaded = mgr.load("migrate")
        assert loaded[0].content == "new"


# ── Serialization ──


class TestSessionSerialization:
    def test_reasoning_details_roundtrip(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        messages = [
            ChatMessage(
                role="assistant",
                content="Need to think",
                reasoning_details="internal reasoning trace",
            ),
        ]

        mgr.save("reasoning", messages)
        loaded = mgr.load("reasoning")

        assert len(loaded) == 1
        assert loaded[0].reasoning_details == "internal reasoning trace"

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


# ── Incremental Writer ──


class TestIncrementalWriter:
    def test_create_writer_and_append(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path)
        info, writer = mgr.create_writer("incremental")
        writer.append(ChatMessage(role="user", content="msg1"))
        writer.append(ChatMessage(role="assistant", content="msg2"))
        writer.close()

        loaded = mgr.load("incremental")
        assert len(loaded) == 2
        assert loaded[0].content == "msg1"

    def test_incremental_crash_recovery(self, tmp_path: Path) -> None:
        """Even if writer isn't closed, flushed messages are recoverable."""
        mgr = SessionManager(storage_dir=tmp_path)
        info, writer = mgr.create_writer("crash")
        writer.append(ChatMessage(role="user", content="before crash"))
        # Simulate crash — don't close writer
        # Message should still be readable  since it was flushed
        loaded = mgr.load("crash")
        assert len(loaded) == 1
        assert loaded[0].content == "before crash"
        writer.close()


class TestSessionInfo:
    def test_fields(self) -> None:
        info = SessionInfo(
            session_id="abc123",
            name="test",
            created_at=1000.0,
            message_count=5,
        )
        assert info.session_id == "abc123"
        assert info.name == "test"
        assert info.message_count == 5

    def test_session_summary_field(self) -> None:
        info = SessionInfo(
            session_id="x",
            name="t",
            created_at=0,
            session_summary="summary text",
        )
        assert info.session_summary == "summary text"
