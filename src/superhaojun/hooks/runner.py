"""Hook runner v2 — executes hooks with structured results and function hook support.

v2 changes from v1:
- Uses HookRegistry.match() instead of HookConfig.get_rules()
- Supports both command and function hook types
- Parses stdout JSON for additional_context / updated_input
- Returns AggregatedHookResult with blocking semantics
- Single run_hooks() entry point replaces run_pre_hooks/run_post_hooks
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .config import (
    AggregatedHookResult, BLOCKING_EVENTS, HookContext, HookEvent,
    HookRegistry, HookResult, HookRule, HookType,
)

logger = logging.getLogger(__name__)


@dataclass
class HookRunner:
    """Executes hooks matched by HookRegistry with structured result aggregation."""
    registry: HookRegistry
    working_dir: str = "."

    async def run_hooks(
        self, event: HookEvent, tool_name: str = "",
        arguments: dict[str, Any] | None = None,
        result: str = "",
        extra: dict[str, Any] | None = None,
    ) -> AggregatedHookResult:
        """Run all matching hooks for an event, return aggregated result."""
        rules = self.registry.match(event, tool_name)
        if not rules:
            return AggregatedHookResult(results=[])

        ctx = HookContext(
            event=event,
            tool_name=tool_name,
            arguments=arguments or {},
            result=result,
            cwd=self.working_dir,
            extra=extra or {},
        )

        results = await asyncio.gather(
            *(self._execute(rule, ctx) for rule in rules),
            return_exceptions=False,
        )
        return AggregatedHookResult(results=list(results))

    async def _execute(self, rule: HookRule, ctx: HookContext) -> HookResult:
        """Execute a single hook rule."""
        if rule.hook_type == HookType.FUNCTION:
            return await self._execute_function(rule, ctx)
        return await self._execute_command(rule, ctx)

    async def _execute_command(self, rule: HookRule, ctx: HookContext) -> HookResult:
        """Execute a shell command hook with variable substitution."""
        cmd = self._substitute(rule.command, ctx)
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=rule.timeout,
            )
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")
            exit_code = proc.returncode or 0
            additional_context, updated_input = self._parse_stdout_json(stdout)

            return HookResult(
                rule=rule,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                additional_context=additional_context,
                updated_input=updated_input,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return HookResult(
                rule=rule, exit_code=1, stdout="", stderr="Hook timed out",
                timed_out=True,
            )
        except OSError as exc:
            return HookResult(
                rule=rule, exit_code=1, stdout="", stderr=str(exc),
            )

    async def _execute_function(self, rule: HookRule, ctx: HookContext) -> HookResult:
        """Execute a Python function hook."""
        if rule.callback is None:
            return HookResult(
                rule=rule, exit_code=1, stdout="", stderr="No callback provided",
            )
        try:
            result = await asyncio.wait_for(
                rule.callback(ctx), timeout=rule.timeout,
            )
            # Function hooks can return a dict with structured fields
            if isinstance(result, dict):
                return HookResult(
                    rule=rule,
                    exit_code=result.get("exit_code", 0),
                    stdout=result.get("stdout", ""),
                    stderr=result.get("stderr", ""),
                    additional_context=result.get("additional_context", ""),
                    updated_input=result.get("updated_input"),
                )
            return HookResult(
                rule=rule, exit_code=0, stdout=str(result) if result else "",
                stderr="",
            )
        except asyncio.TimeoutError:
            return HookResult(
                rule=rule, exit_code=1, stdout="", stderr="Function hook timed out",
                timed_out=True,
            )
        except Exception as exc:
            return HookResult(
                rule=rule, exit_code=1, stdout="", stderr=str(exc),
            )

    @staticmethod
    def _substitute(template: str, ctx: HookContext) -> str:
        """Variable substitution for shell command templates."""
        result = template
        result = result.replace("$TOOL_NAME", ctx.tool_name)
        result = result.replace("$EVENT", ctx.event.value)
        result = result.replace("$CWD", ctx.cwd)
        result = result.replace("$RESULT", ctx.result)
        if ctx.arguments:
            result = result.replace("$ARGUMENTS", json.dumps(ctx.arguments))
        else:
            result = result.replace("$ARGUMENTS", "{}")
        return result

    @staticmethod
    def _parse_stdout_json(stdout: str) -> tuple[str, dict[str, Any] | None]:
        """Parse stdout for structured JSON output.

        Hooks can output JSON with:
        - additional_context: string to append to agent context
        - updated_input: dict to replace tool arguments
        """
        if not stdout.strip():
            return "", None
        try:
            data = json.loads(stdout.strip())
            if isinstance(data, dict):
                return (
                    data.get("additional_context", ""),
                    data.get("updated_input"),
                )
        except (json.JSONDecodeError, ValueError):
            pass
        return "", None
