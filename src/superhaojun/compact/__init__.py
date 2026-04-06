"""Compact package — context compaction with circuit breaker + session compact."""

from .compactor import CompactionResult, ContextCompactor, estimate_tokens
from .prompts import COMPACTION_SYSTEM_PROMPT, COMPACTION_USER_PROMPT, SESSION_SUMMARY_PROMPT
from .session_compact import compact_session

__all__ = [
    "COMPACTION_SYSTEM_PROMPT",
    "COMPACTION_USER_PROMPT",
    "SESSION_SUMMARY_PROMPT",
    "CompactionResult",
    "ContextCompactor",
    "compact_session",
    "estimate_tokens",
]
