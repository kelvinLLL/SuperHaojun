"""HookRunner — executes shell hook commands before/after tool calls.

Hooks run as subprocess commands with variable substitution.
Pre-hooks can block tool execution (non-zero exit = abort).
Post-hooks are fire-and-forget (failures logged, don't affect tool result).

Reference: Claude Code's `utils/hooks/` with frontmatter-based hooks.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .config import HookConfig, HookRule, HookTiming

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HookResult:
    """Result of a single hook execution."""
    rule: HookRule
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass
class HookRunner:
    """Executes hook commands for tool calls.

    Usage:
        runner = HookRunner(config)

        # Pre-hooks: if any fail, tool should not execute
        pre_results = await runner.run_pre_hooks("bash", {"command": "ls"})
        if not runner.all_passed(pre_results):
            return "Blocked by pre-hook"

        # ... execute tool ...

        # Post-hooks: fire-and-forget
        await runner.run_post_hooks("bash", {"command": "ls"}, result="file1\\nfile2")
    """
    config: HookConfig
    working_dir: str = "."

    async def run_pre_hooks(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> list[HookResult]:
        """Run all matching pre-hooks. Returns results for each."""
        rules = self.config.get_rules(tool_name, HookTiming.PRE)
        if not rules:
            return []
        return await asyncio.gather(
            *(self._execute(rule, tool_name, arguments) for rule in rules)
        )

    async def run_post_hooks(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: str = "",
    ) -> list[HookResult]:
        """Run all matching post-hooks. Failures are logged but non-blocking."""
        rules = self.config.get_rules(tool_name, HookTiming.POST)
        if not rules:
            return []
        return await asyncio.gather(
            *(self._execute(rule, tool_name, arguments, result) for rule in rules)
        )

    @staticmethod
    def all_passed(results: list[HookResult]) -> bool:
        """Check if all hook results are successful."""
        return all(r.success for r in results)

    async def _execute(
        self,
        rule: HookRule,
        tool_name: str,
        arguments: dict[str, Any],
        result: str = "",
    ) -> HookResult:
        """Execute a single hook command with variable substitution."""
        # Substitute placeholders
        args_str = json.dumps(arguments, ensure_ascii=False)
        try:
            command = rule.command.format(
                tool_name=tool_name,
                arguments=args_str,
                result=result,
                cwd=self.working_dir,
            )
        except (KeyError, IndexError, ValueError):
            # If template has unknown placeholders, run as-is
            command = rule.command

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=rule.timeout,
            )
            return HookResult(
                rule=rule,
                exit_code=proc.returncode or 0,
                stdout=stdout_bytes.decode("utf-8", errors="replace").strip(),
                stderr=stderr_bytes.decode("utf-8", errors="replace").strip(),
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()  # type: ignore[union-attr]
            except ProcessLookupError:
                pass
            logger.warning("Hook timed out after %ds: %s", rule.timeout, command)
            return HookResult(
                rule=rule, exit_code=-1, stdout="", stderr="Timed out", timed_out=True,
            )
        except Exception as exc:
            logger.warning("Hook execution failed: %s — %s", command, exc)
            return HookResult(
                rule=rule, exit_code=-1, stdout="", stderr=str(exc),
            )
