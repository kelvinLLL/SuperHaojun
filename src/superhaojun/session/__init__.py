"""Session package — JSONL-based conversation persistence."""

from .manager import SessionInfo, SessionManager, SessionWriter

__all__ = ["SessionInfo", "SessionManager", "SessionWriter"]
