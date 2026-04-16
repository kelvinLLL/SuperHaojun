"""SessionManager v2 — JSONL incremental write with backward compatibility.

Key improvements over v1:
- Append-only JSONL: each message written immediately + flushed (crash-safe)
- Header line: session metadata stored as first JSONL line
- Backward compatibility: detects old JSON format and reads it correctly
- SessionWriter: manages file handle lifecycle for append operations
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

from ..conversation import ChatMessage


@dataclass(frozen=True)
class SessionInfo:
    """Metadata about a saved session."""
    session_id: str
    name: str
    created_at: float
    message_count: int = 0
    session_summary: str = ""


def _message_to_dict(msg: ChatMessage) -> dict[str, Any]:
    data = msg.to_dict()
    data["type"] = "message"
    return data


def _message_from_dict(data: dict[str, Any]) -> ChatMessage:
    return ChatMessage.from_dict(data)


class SessionWriter:
    """Incremental JSONL session writer — append + flush per message."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file: TextIO | None = None

    def _ensure_open(self) -> TextIO:
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self._path.open("a", encoding="utf-8")
        return self._file

    def write_header(self, info: SessionInfo) -> None:
        """Write session metadata as the first JSONL line."""
        header = {
            "type": "header",
            "session_id": info.session_id,
            "name": info.name,
            "created_at": info.created_at,
            "session_summary": info.session_summary,
        }
        f = self._ensure_open()
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
        f.flush()

    def append(self, message: ChatMessage) -> None:
        """Append a single message to the JSONL file."""
        f = self._ensure_open()
        f.write(json.dumps(_message_to_dict(message), ensure_ascii=False) + "\n")
        f.flush()

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    def __enter__(self) -> SessionWriter:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def _is_jsonl(path: Path) -> bool:
    """Detect if file is JSONL (multiple lines, each valid JSON) vs single JSON."""
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return False
        first_line = text.split("\n", 1)[0].strip()
        obj = json.loads(first_line)
        # JSONL has "type" field in header; old JSON has "messages" array
        return "type" in obj
    except (json.JSONDecodeError, OSError):
        return False


def _load_legacy_json(path: Path) -> tuple[dict[str, Any] | None, list[ChatMessage]]:
    """Load old-format JSON session file. Returns (metadata, messages)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "messages" not in data:
            return None, []
        messages = [_message_from_dict(m) for m in data.get("messages", [])]
        return data, messages
    except (json.JSONDecodeError, OSError, KeyError):
        return None, []


def _load_jsonl(path: Path) -> tuple[dict[str, Any] | None, list[ChatMessage]]:
    """Load JSONL session file. Returns (header_metadata, messages)."""
    header: dict[str, Any] | None = None
    messages: list[ChatMessage] = []
    try:
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue  # Skip corrupted lines
            if obj.get("type") == "header":
                header = obj
            elif obj.get("type") == "message":
                messages.append(_message_from_dict(obj))
    except OSError:
        pass
    return header, messages


class SessionManager:
    """Manages session persistence with JSONL incremental storage.

    New sessions use .jsonl format. Old .json files are read with backward
    compatibility but new writes always use JSONL.
    """

    def __init__(self, storage_dir: Path | str) -> None:
        self._storage_dir = Path(storage_dir)

    def _ensure_dir(self) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _safe_name(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)

    def _session_path(self, name: str) -> Path:
        """JSONL path for new format."""
        return self._storage_dir / f"{self._safe_name(name)}.jsonl"

    def _legacy_path(self, name: str) -> Path:
        """JSON path for old format (backward compat)."""
        return self._storage_dir / f"{self._safe_name(name)}.json"

    def _find_session_file(self, name: str) -> Path | None:
        """Find session file — prefer JSONL, fall back to legacy JSON."""
        jsonl = self._session_path(name)
        if jsonl.exists():
            return jsonl
        json_path = self._legacy_path(name)
        if json_path.exists():
            return json_path
        return None

    def create(self, name: str) -> SessionInfo:
        return SessionInfo(
            session_id=uuid4().hex,
            name=name,
            created_at=time.time(),
        )

    def save(self, name: str, messages: list[ChatMessage], session_summary: str = "") -> SessionInfo:
        """Save messages to a JSONL session file (full rewrite)."""
        self._ensure_dir()
        path = self._session_path(name)

        # Load existing metadata if overwriting
        existing_info = self._load_info(name)
        session_id = existing_info.session_id if existing_info else uuid4().hex
        created_at = existing_info.created_at if existing_info else time.time()

        info = SessionInfo(
            session_id=session_id,
            name=name,
            created_at=created_at,
            message_count=len(messages),
            session_summary=session_summary,
        )

        # Remove legacy JSON if exists
        legacy = self._legacy_path(name)
        if legacy.exists():
            legacy.unlink()

        # Write fresh JSONL
        if path.exists():
            path.unlink()
        with SessionWriter(path) as writer:
            writer.write_header(info)
            for msg in messages:
                writer.append(msg)

        return info

    def create_writer(self, name: str, session_summary: str = "") -> tuple[SessionInfo, SessionWriter]:
        """Create a SessionWriter for incremental append.

        Returns (SessionInfo, SessionWriter). Call writer.close() when done.
        """
        self._ensure_dir()
        path = self._session_path(name)

        info = SessionInfo(
            session_id=uuid4().hex,
            name=name,
            created_at=time.time(),
            session_summary=session_summary,
        )

        if path.exists():
            path.unlink()

        writer = SessionWriter(path)
        writer.write_header(info)
        return info, writer

    def load(self, name: str) -> list[ChatMessage]:
        """Load messages from a session. Handles both JSONL and legacy JSON."""
        path = self._find_session_file(name)
        if path is None:
            return []

        if path.suffix == ".json" or not _is_jsonl(path):
            _, messages = _load_legacy_json(path)
        else:
            _, messages = _load_jsonl(path)
        return messages

    def list_sessions(self) -> list[SessionInfo]:
        """List all saved sessions, most recent first."""
        if not self._storage_dir.exists():
            return []
        sessions: list[SessionInfo] = []

        for path in sorted(self._storage_dir.iterdir()):
            if path.suffix not in (".jsonl", ".json"):
                continue
            info = self._load_info_from_path(path)
            if info:
                sessions.append(info)

        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions

    def delete(self, name: str) -> bool:
        """Delete a session file."""
        path = self._find_session_file(name)
        if path and path.exists():
            path.unlink()
            return True
        return False

    def _load_info(self, name: str) -> SessionInfo | None:
        path = self._find_session_file(name)
        if path is None:
            return None
        return self._load_info_from_path(path)

    def _load_info_from_path(self, path: Path) -> SessionInfo | None:
        if path.suffix == ".json" or not _is_jsonl(path):
            data, messages = _load_legacy_json(path)
            if data is None:
                return None
            return SessionInfo(
                session_id=data.get("session_id", ""),
                name=data.get("name", path.stem),
                created_at=data.get("created_at", 0),
                message_count=data.get("message_count", len(messages)),
            )
        else:
            header, messages = _load_jsonl(path)
            if header is None:
                return None
            return SessionInfo(
                session_id=header.get("session_id", ""),
                name=header.get("name", path.stem),
                created_at=header.get("created_at", 0),
                message_count=len(messages),
                session_summary=header.get("session_summary", ""),
            )
