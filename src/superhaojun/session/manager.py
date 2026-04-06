"""SessionManager — save / load / list / delete conversation sessions.

Sessions are stored as JSON files in a configurable directory.
Each file contains session metadata + serialized ChatMessage list.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..agent import ChatMessage


@dataclass(frozen=True)
class SessionInfo:
    """Metadata about a saved session."""
    session_id: str
    name: str
    created_at: float
    message_count: int = 0


def _message_to_dict(msg: ChatMessage) -> dict[str, Any]:
    return {
        "role": msg.role,
        "content": msg.content,
        "tool_calls": msg.tool_calls,
        "tool_call_id": msg.tool_call_id,
        "name": msg.name,
    }


def _message_from_dict(data: dict[str, Any]) -> ChatMessage:
    return ChatMessage(
        role=data["role"],
        content=data.get("content"),
        tool_calls=data.get("tool_calls"),
        tool_call_id=data.get("tool_call_id"),
        name=data.get("name"),
    )


class SessionManager:
    """Manages session persistence with JSON file storage."""

    def __init__(self, storage_dir: Path | str) -> None:
        self._storage_dir = Path(storage_dir)

    def _ensure_dir(self) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, name: str) -> Path:
        # Sanitize name for filesystem safety
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return self._storage_dir / f"{safe_name}.json"

    def create(self, name: str) -> SessionInfo:
        """Create a new session (metadata only, no messages yet)."""
        return SessionInfo(
            session_id=uuid4().hex,
            name=name,
            created_at=time.time(),
        )

    def save(self, name: str, messages: list[ChatMessage]) -> SessionInfo:
        """Save messages to a named session file."""
        self._ensure_dir()
        path = self._session_path(name)

        # Load existing session ID if overwriting, else create new
        existing = self._load_raw(path)
        session_id = existing.get("session_id", uuid4().hex) if existing else uuid4().hex
        created_at = existing.get("created_at", time.time()) if existing else time.time()

        data = {
            "session_id": session_id,
            "name": name,
            "created_at": created_at,
            "updated_at": time.time(),
            "message_count": len(messages),
            "messages": [_message_to_dict(m) for m in messages],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return SessionInfo(
            session_id=session_id,
            name=name,
            created_at=created_at,
            message_count=len(messages),
        )

    def load(self, name: str) -> list[ChatMessage]:
        """Load messages from a named session. Returns empty list if not found."""
        path = self._session_path(name)
        data = self._load_raw(path)
        if not data:
            return []
        return [_message_from_dict(m) for m in data.get("messages", [])]

    def list_sessions(self) -> list[SessionInfo]:
        """List all saved sessions, most recently updated first."""
        if not self._storage_dir.exists():
            return []
        sessions: list[SessionInfo] = []
        for path in self._storage_dir.glob("*.json"):
            data = self._load_raw(path)
            if data:
                sessions.append(SessionInfo(
                    session_id=data.get("session_id", ""),
                    name=data.get("name", path.stem),
                    created_at=data.get("created_at", 0),
                    message_count=data.get("message_count", 0),
                ))
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions

    def delete(self, name: str) -> bool:
        """Delete a session file. Returns True if deleted, False if not found."""
        path = self._session_path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def _load_raw(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
