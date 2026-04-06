"""Permission rules — define how tool access is decided."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass(frozen=True)
class PermissionRule:
    """A rule that maps a tool or risk_level to a Decision.

    Matching priority: tool_name match > risk_level match > default.
    """
    tool_name: str | None = None
    risk_level: str | None = None
    decision: Decision = Decision.ASK
