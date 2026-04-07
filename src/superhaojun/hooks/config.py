"""Hook configuration v2 — expanded lifecycle events, multiple hook types, and registry.

v2 changes from v1:
- HookEvent: 2 → 15 lifecycle events (session, user prompt, tool, stop, compact, subagent, env)
- HookType: 1 → 2 types (command + function)
- HookResult: structured fields (additional_context, updated_input, blocking)
- HookRegistry: multi-source rule management with priority

Reference: Claude Code's ~3,721 line hook system (17 files).
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Awaitable


class HookEvent(StrEnum):
    """Lifecycle events that hooks can intercept."""
    # Session lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    # User interaction
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    # Tool execution
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    # Agent output
    STOP = "stop"
    STOP_FAILURE = "stop_failure"
    # Compaction
    PRE_COMPACT = "pre_compact"
    POST_COMPACT = "post_compact"
    # Sub-Agent
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"
    # Environment changes
    FILE_CHANGED = "file_changed"
    CWD_CHANGED = "cwd_changed"
    CONFIG_CHANGE = "config_change"


# Blocking events: exit_code=2 blocks/re-prompts
BLOCKING_EVENTS = frozenset({
    HookEvent.PRE_TOOL_USE,
    HookEvent.USER_PROMPT_SUBMIT,
    HookEvent.STOP,
})


class HookType(StrEnum):
    COMMAND = "command"
    FUNCTION = "function"


@dataclass(frozen=True)
class HookRule:
    """A single hook rule.

    Attributes:
        tool_pattern: glob pattern or exact name. For non-tool events use "*".
        event: lifecycle event to intercept.
        hook_type: "command" or "function".
        command: shell command template (for command type).
        callback: async callable (for function type, session-only).
        timeout: max execution seconds (command type).
        enabled: whether this rule is active.
        priority: lower = runs first.
    """
    tool_pattern: str
    event: HookEvent
    hook_type: HookType = HookType.COMMAND
    command: str = ""
    callback: Callable[..., Awaitable[Any]] | None = None
    timeout: int = 10
    enabled: bool = True
    priority: int = 100

    def matches(self, tool_name: str = "") -> bool:
        if not tool_name or self.tool_pattern == "*":
            return True
        return fnmatch.fnmatch(tool_name, self.tool_pattern)


@dataclass(frozen=True)
class HookContext:
    """Context passed to hook execution."""
    event: HookEvent
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    cwd: str = "."
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HookResult:
    """Result of a single hook execution.

    Exit code semantics (aligned with CC):
    - 0: success
    - 2: blocking error (abort tool / re-prompt)
    - other: non-blocking error (logged, not fatal)
    """
    rule: HookRule
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    additional_context: str = ""
    updated_input: dict[str, Any] | None = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def blocking(self) -> bool:
        return self.exit_code == 2


@dataclass(frozen=True)
class AggregatedHookResult:
    """Aggregated results from all hooks for a single event."""
    results: list[HookResult]

    @property
    def blocking_errors(self) -> list[str]:
        return [r.stderr or r.stdout for r in self.results if r.blocking]

    @property
    def additional_contexts(self) -> list[str]:
        return [r.additional_context for r in self.results if r.additional_context]

    @property
    def updated_input(self) -> dict[str, Any] | None:
        for r in reversed(self.results):
            if r.updated_input is not None:
                return r.updated_input
        return None

    @property
    def should_block(self) -> bool:
        return any(r.blocking for r in self.results)

    @property
    def all_passed(self) -> bool:
        return all(r.success for r in self.results)


@dataclass
class HookRegistry:
    """Multi-source hook rule management with priority-based matching.

    Sources:
    - Config hooks: loaded from .haojun/hooks.json (persistent)
    - Runtime hooks: added via add_hook() (session-scoped)
    - Function hooks: Python callbacks (session-scoped, internal)
    """
    _config_rules: list[HookRule] = field(default_factory=list)
    _runtime_rules: list[HookRule] = field(default_factory=list)

    def add_rule(self, rule: HookRule) -> None:
        self._runtime_rules.append(rule)

    def remove_rule(self, index: int) -> bool:
        if 0 <= index < len(self._runtime_rules):
            self._runtime_rules.pop(index)
            return True
        return False

    def match(self, event: HookEvent, tool_name: str = "") -> list[HookRule]:
        all_rules = self._config_rules + self._runtime_rules
        matched = [
            r for r in all_rules
            if r.enabled and r.event == event and r.matches(tool_name)
        ]
        return sorted(matched, key=lambda r: r.priority)

    def list_hooks(self) -> list[HookRule]:
        return list(self._config_rules + self._runtime_rules)

    def clear_runtime(self) -> None:
        self._runtime_rules.clear()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "hooks": [
                {
                    "tool_pattern": r.tool_pattern,
                    "event": r.event.value,
                    "command": r.command,
                    "timeout": r.timeout,
                    "enabled": r.enabled,
                    "priority": r.priority,
                }
                for r in self._config_rules
                if r.hook_type == HookType.COMMAND
            ]
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> HookRegistry:
        registry = cls()
        if not path.is_file():
            return registry
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return registry
        for item in data.get("hooks", []):
            if not isinstance(item, dict):
                continue
            try:
                event_str = item.get("event") or item.get("timing")
                if event_str in ("pre", "pre_tool_use"):
                    event = HookEvent.PRE_TOOL_USE
                elif event_str in ("post", "post_tool_use"):
                    event = HookEvent.POST_TOOL_USE
                else:
                    event = HookEvent(event_str)
                registry._config_rules.append(HookRule(
                    tool_pattern=item["tool_pattern"],
                    event=event,
                    hook_type=HookType.COMMAND,
                    command=item["command"],
                    timeout=item.get("timeout", 10),
                    enabled=item.get("enabled", True),
                    priority=item.get("priority", 100),
                ))
            except (KeyError, ValueError):
                continue
        return registry
