"""Hook configuration — rules defining when and what hooks fire.

Hook rules are loaded from a settings file (.haojun/hooks.json) or
programmatically. Each rule specifies:
- Which tools it applies to (glob pattern or exact name)
- When it fires (pre / post / both)
- What it runs (shell command template with variable substitution)

Reference: Claude Code's `utils/hooks/` frontmatter-based hook system.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class HookTiming(StrEnum):
    PRE = "pre"
    POST = "post"


@dataclass(frozen=True)
class HookRule:
    """A single hook rule.

    Attributes:
        tool_pattern: Glob pattern or exact tool name (e.g. "bash", "write_*").
        timing: When to fire — before or after tool execution.
        command: Shell command template. Supports placeholders:
            {tool_name}, {arguments}, {result} (post only), {cwd}.
        timeout: Max seconds for the hook command (default 10).
        enabled: Whether this rule is active.
    """
    tool_pattern: str
    timing: HookTiming
    command: str
    timeout: int = 10
    enabled: bool = True

    def matches(self, tool_name: str) -> bool:
        """Check if this rule applies to the given tool name."""
        return fnmatch.fnmatch(tool_name, self.tool_pattern)


@dataclass
class HookConfig:
    """Collection of hook rules, loadable from JSON settings file.

    Settings file format (.haojun/hooks.json):
    ```json
    {
        "hooks": [
            {
                "tool_pattern": "bash",
                "timing": "pre",
                "command": "echo 'About to run bash: {arguments}'",
                "timeout": 5
            },
            {
                "tool_pattern": "write_*",
                "timing": "post",
                "command": "echo 'Wrote file' >> /tmp/hook.log"
            }
        ]
    }
    ```
    """
    rules: list[HookRule] = field(default_factory=list)

    def add_rule(self, rule: HookRule) -> None:
        self.rules.append(rule)

    def remove_rule(self, index: int) -> bool:
        if 0 <= index < len(self.rules):
            self.rules.pop(index)
            return True
        return False

    def get_rules(self, tool_name: str, timing: HookTiming) -> list[HookRule]:
        """Get all enabled rules matching a tool name and timing."""
        return [
            r for r in self.rules
            if r.enabled and r.timing == timing and r.matches(tool_name)
        ]

    def save(self, path: Path) -> None:
        """Save hook config to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "hooks": [
                {
                    "tool_pattern": r.tool_pattern,
                    "timing": r.timing.value,
                    "command": r.command,
                    "timeout": r.timeout,
                    "enabled": r.enabled,
                }
                for r in self.rules
            ]
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> HookConfig:
        """Load hook config from JSON file. Returns empty config if file missing."""
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        rules: list[HookRule] = []
        for item in data.get("hooks", []):
            if not isinstance(item, dict):
                continue
            try:
                rules.append(HookRule(
                    tool_pattern=item["tool_pattern"],
                    timing=HookTiming(item["timing"]),
                    command=item["command"],
                    timeout=item.get("timeout", 10),
                    enabled=item.get("enabled", True),
                ))
            except (KeyError, ValueError):
                continue  # Skip malformed rules
        return cls(rules=rules)
