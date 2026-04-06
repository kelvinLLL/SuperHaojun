"""Agent loop: manages conversation history and communicates via MessageBus."""

from __future__ import annotations

import asyncio
import json
import httpx
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI, NOT_GIVEN
from openai.types.chat import ChatCompletionMessageParam

from .bus import MessageBus
from .compact.compactor import ContextCompactor
from .config import ModelConfig, make_permissive_ssl_context
from .messages import (
    AgentEnd, AgentStart, Error,
    PermissionRequest, TextDelta,
    ToolCallEnd, ToolCallStart, TurnEnd, TurnStart,
)
from .permissions import Decision, PermissionChecker
from .prompt.builder import SystemPromptBuilder
from .tools.registry import ToolRegistry


@dataclass
class ChatMessage:
    """A single message in the conversation history."""
    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolCallInfo:
    """Accumulated tool call from a streamed response."""
    id: str
    name: str
    arguments: str


@dataclass
class Agent:
    """Stateful conversation agent that communicates via MessageBus.

    Instead of yielding events, the agent emits structured messages through
    the bus. Permission flow uses bus.expect() + bus.emit() for true
    request-response across any transport boundary.
    """

    config: ModelConfig
    bus: MessageBus
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    permission_checker: PermissionChecker = field(default_factory=PermissionChecker)
    prompt_builder: SystemPromptBuilder | None = None
    compactor: ContextCompactor | None = None
    system_prompt: str = ""
    messages: list[ChatMessage] = field(default_factory=list)
    _client: AsyncOpenAI | None = field(default=None, repr=False)

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            ssl_ctx = make_permissive_ssl_context()
            http_client = httpx.AsyncClient(verify=ssl_ctx)
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                http_client=http_client,
            )
        return self._client

    def _build_messages(self) -> list[ChatCompletionMessageParam]:
        prompt = self.prompt_builder.build() if self.prompt_builder else self.system_prompt
        msgs: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": prompt},
        ]
        for m in self.messages:
            if m.role == "tool":
                msgs.append({
                    "role": "tool",
                    "content": m.content or "",
                    "tool_call_id": m.tool_call_id or "",
                })  # type: ignore[arg-type]
            elif m.role == "assistant" and m.tool_calls:
                msg: dict[str, Any] = {"role": "assistant"}
                if m.content:
                    msg["content"] = m.content
                else:
                    msg["content"] = None
                msg["tool_calls"] = m.tool_calls
                msgs.append(msg)  # type: ignore[arg-type]
            else:
                msgs.append({"role": m.role, "content": m.content or ""})  # type: ignore[arg-type]
        return msgs

    async def handle_user_message(self, user_input: str) -> None:
        """Process a user message. Emits events via MessageBus."""
        self.messages.append(ChatMessage(role="user", content=user_input))
        await self.bus.emit(AgentStart())

        while True:
            await self.bus.emit(TurnStart())

            tools_param = self.registry.to_openai_tools() if len(self.registry) > 0 else None

            stream = await self.client.chat.completions.create(
                model=self.config.model_id,
                messages=self._build_messages(),
                tools=tools_param if tools_param else NOT_GIVEN,
                stream=True,
            )

            text_chunks: list[str] = []
            tool_calls_buf: dict[int, ToolCallInfo] = {}
            finish_reason: str | None = None

            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                delta = choice.delta

                if delta and delta.content:
                    text_chunks.append(delta.content)
                    await self.bus.emit(TextDelta(text=delta.content))

                if delta and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_buf:
                            tool_calls_buf[idx] = ToolCallInfo(
                                id=tc_delta.id or "",
                                name=tc_delta.function.name if tc_delta.function and tc_delta.function.name else "",
                                arguments=tc_delta.function.arguments if tc_delta.function and tc_delta.function.arguments else "",
                            )
                        else:
                            existing = tool_calls_buf[idx]
                            if tc_delta.id:
                                existing.id = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    existing.name += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    existing.arguments += tc_delta.function.arguments

            await self.bus.emit(TurnEnd(finish_reason=finish_reason or "stop"))

            if finish_reason == "tool_calls" and tool_calls_buf:
                sorted_calls = [tool_calls_buf[i] for i in sorted(tool_calls_buf)]

                self.messages.append(ChatMessage(
                    role="assistant",
                    content="".join(text_chunks) if text_chunks else None,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in sorted_calls
                    ],
                ))

                await self._execute_tool_calls(sorted_calls)
                continue

            self.messages.append(ChatMessage(role="assistant", content="".join(text_chunks)))
            break

        await self.bus.emit(AgentEnd())

        # Auto-compact if approaching token limit
        if self.compactor and self.compactor.should_compact(self.messages):
            await self._auto_compact()

    async def _execute_tool_calls(self, tool_calls: list[ToolCallInfo]) -> None:
        """Execute tool calls with concurrent/sequential strategy."""
        concurrent: list[ToolCallInfo] = []
        sequential: list[ToolCallInfo] = []

        for tc in tool_calls:
            tool = self.registry.get(tc.name)
            if tool and tool.is_concurrent_safe:
                concurrent.append(tc)
            else:
                sequential.append(tc)

        if concurrent:
            results = await asyncio.gather(
                *(self._run_one_tool(tc) for tc in concurrent),
                return_exceptions=True,
            )
            for tc, result_or_exc in zip(concurrent, results):
                self._append_tool_result(tc, result_or_exc)

        for tc in sequential:
            result = await self._run_one_tool(tc)
            self._append_tool_result(tc, result)

    async def _run_one_tool(self, tc: ToolCallInfo) -> str:
        """Run a tool with permission checking. Emits messages via bus."""
        tool = self.registry.get(tc.name)
        if tool is None:
            return f"Error: unknown tool '{tc.name}'"

        try:
            kwargs = json.loads(tc.arguments) if tc.arguments else {}
        except json.JSONDecodeError as exc:
            return f"Error: invalid tool arguments: {exc}"

        # Permission check
        decision = self.permission_checker.check(tc.name, tool.risk_level)
        if decision == Decision.DENY:
            return f"Permission denied for tool '{tc.name}'"
        if decision == Decision.ASK:
            # Set up waiter BEFORE emitting request (so handler can respond)
            future = self.bus.expect("permission_response", match_id=tc.id)
            await self.bus.emit(PermissionRequest(
                tool_call_id=tc.id, tool_name=tc.name,
                arguments=kwargs, risk_level=tool.risk_level,
            ))
            response = await future
            if not response.granted:
                return f"Permission denied for tool '{tc.name}'"

        await self.bus.emit(ToolCallStart(
            tool_call_id=tc.id, tool_name=tc.name, arguments=kwargs,
        ))

        try:
            result = await tool.execute(**kwargs)
        except Exception as exc:
            result = f"Error executing tool '{tc.name}': {exc}"

        await self.bus.emit(ToolCallEnd(
            tool_call_id=tc.id, tool_name=tc.name, result=result,
        ))

        return result

    def _append_tool_result(self, tc: ToolCallInfo, result: str | BaseException) -> None:
        if isinstance(result, BaseException):
            content = f"Error executing tool '{tc.name}': {result}"
        else:
            content = result
        self.messages.append(ChatMessage(
            role="tool",
            content=content,
            tool_call_id=tc.id,
            name=tc.name,
        ))

    async def _auto_compact(self) -> None:
        """Compact conversation when token threshold is exceeded."""
        if not self.compactor:
            return
        result = await self.compactor.compact(self.messages)
        if result.removed_count == 0:
            return
        # Replace messages: summary boundary + preserved tail
        preserved = self.messages[len(self.messages) - result.preserved_count:]
        self.messages.clear()
        self.messages.extend(result.to_messages())
        self.messages.extend(preserved)
        # Invalidate prompt cache since context changed
        if self.prompt_builder:
            self.prompt_builder.invalidate()

    def reset(self) -> None:
        self.messages.clear()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
