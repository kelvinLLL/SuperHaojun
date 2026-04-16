"""Tool execution orchestration extracted from the main agent loop."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable

from .conversation import ChatMessage
from .hooks.config import HookEvent
from .hooks.runner import HookRunner
from .messages import PermissionRequest, ToolCallEnd, ToolCallStart
from .permissions import Decision, PermissionChecker
from .tools.registry import ToolRegistry


@dataclass
class ToolCallInfo:
    """Accumulated tool call from a streamed response."""

    id: str
    name: str
    arguments: str


@dataclass
class ToolExecutionResult:
    """Normalized result from one tool execution."""

    tool_call: ToolCallInfo
    content: str

    def to_message(self) -> ChatMessage:
        return ChatMessage(
            role="tool",
            content=self.content,
            tool_call_id=self.tool_call.id,
            name=self.tool_call.name,
        )


@dataclass
class ToolOrchestrator:
    """Owns batching, permissions, hooks, and per-tool execution."""

    bus: Any
    registry: ToolRegistry
    permission_checker: PermissionChecker
    hook_runner: HookRunner | None = None
    status_callback: Callable[[ToolCallInfo, str, str | None], None] | None = None

    async def execute_tool_calls(
        self,
        tool_calls: list[ToolCallInfo],
    ) -> list[ToolExecutionResult]:
        concurrent: list[ToolCallInfo] = []
        sequential: list[ToolCallInfo] = []

        for tool_call in tool_calls:
            tool = self.registry.get(tool_call.name)
            if tool and tool.is_concurrent_safe:
                concurrent.append(tool_call)
            else:
                sequential.append(tool_call)

        results: list[ToolExecutionResult] = []

        if concurrent:
            concurrent_results = await asyncio.gather(
                *(self.execute_tool_call(tool_call) for tool_call in concurrent),
                return_exceptions=True,
            )
            for tool_call, result_or_exc in zip(concurrent, concurrent_results):
                results.append(self._normalize_result(tool_call, result_or_exc))

        for tool_call in sequential:
            result = await self.execute_tool_call(tool_call)
            results.append(result)

        return results

    async def execute_tool_call(self, tool_call: ToolCallInfo) -> ToolExecutionResult:
        tool = self.registry.get(tool_call.name)
        if tool is None:
            result = ToolExecutionResult(
                tool_call=tool_call,
                content=f"Error: unknown tool '{tool_call.name}'",
            )
            self._report_status(tool_call, "failed", result.content)
            await self._emit_terminal_result(tool_call, result.content)
            return result

        try:
            kwargs = json.loads(tool_call.arguments) if tool_call.arguments else {}
        except json.JSONDecodeError as exc:
            result = ToolExecutionResult(
                tool_call=tool_call,
                content=f"Error: invalid tool arguments: {exc}",
            )
            self._report_status(tool_call, "failed", result.content)
            await self._emit_terminal_result(tool_call, result.content)
            return result

        decision = self.permission_checker.check(tool_call.name, tool.risk_level)
        if decision == Decision.DENY:
            result = ToolExecutionResult(
                tool_call=tool_call,
                content=f"Permission denied for tool '{tool_call.name}'",
            )
            self._report_status(tool_call, "blocked", result.content)
            await self._emit_terminal_result(tool_call, result.content)
            return result
        if decision == Decision.ASK:
            future = self.bus.expect("permission_response", match_id=tool_call.id)
            await self.bus.emit(PermissionRequest(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                arguments=kwargs,
                risk_level=tool.risk_level,
            ))
            response = await future
            if not response.granted:
                result = ToolExecutionResult(
                    tool_call=tool_call,
                    content=f"Permission denied for tool '{tool_call.name}'",
                )
                self._report_status(tool_call, "blocked", result.content)
                await self._emit_terminal_result(tool_call, result.content)
                return result

        self._report_status(tool_call, "running", None)
        await self.bus.emit(ToolCallStart(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            arguments=kwargs,
        ))

        if self.hook_runner:
            agg = await self.hook_runner.run_hooks(
                HookEvent.PRE_TOOL_USE,
                tool_name=tool_call.name,
                arguments=kwargs,
            )
            if agg.should_block:
                result = (
                    f"Blocked by hook for tool '{tool_call.name}': "
                    f"{'; '.join(agg.blocking_errors)}"
                )
                self._report_status(tool_call, "blocked", result)
                await self._emit_terminal_result(tool_call, result)
                return ToolExecutionResult(tool_call=tool_call, content=result)
            if agg.updated_input:
                kwargs = agg.updated_input

        try:
            result = await tool.execute(**kwargs)
        except Exception as exc:
            result = f"Error executing tool '{tool_call.name}': {exc}"
            terminal_status = "failed"
        else:
            terminal_status = "completed"

        if self.hook_runner:
            agg = await self.hook_runner.run_hooks(
                HookEvent.POST_TOOL_USE,
                tool_name=tool_call.name,
                arguments=kwargs,
                result=result,
            )
            if agg.additional_contexts:
                result += "\n[Hook] " + "\n[Hook] ".join(agg.additional_contexts)

        self._report_status(tool_call, terminal_status, result)
        await self._emit_terminal_result(tool_call, result)
        return ToolExecutionResult(tool_call=tool_call, content=result)

    @staticmethod
    def _normalize_result(
        tool_call: ToolCallInfo,
        result_or_exc: ToolExecutionResult | BaseException,
    ) -> ToolExecutionResult:
        if isinstance(result_or_exc, BaseException):
            return ToolExecutionResult(
                tool_call=tool_call,
                content=f"Error executing tool '{tool_call.name}': {result_or_exc}",
            )
        return result_or_exc

    def _report_status(
        self,
        tool_call: ToolCallInfo,
        status: str,
        detail: str | None,
    ) -> None:
        if self.status_callback is not None:
            self.status_callback(tool_call, status, detail)

    async def _emit_terminal_result(self, tool_call: ToolCallInfo, result: str) -> None:
        await self.bus.emit(ToolCallEnd(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            result=result,
        ))
