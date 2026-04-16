"""Agent loop: manages conversation history and communicates via MessageBus."""

from __future__ import annotations

import httpx
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from .bus import MessageBus
from .compact.compactor import ContextCompactor
from .config import ModelConfig, make_permissive_ssl_context
from .conversation import ChatMessage, ConversationState
from .hooks.config import HookEvent
from .hooks.runner import HookRunner
from .messages import (
    AgentEnd, AgentStart, Error,
    TextDelta, TurnEnd, TurnStart,
)
from .permissions import PermissionChecker
from .prompt.builder import SystemPromptBuilder
from .tool_orchestration import ToolCallInfo, ToolOrchestrator
from .tools.registry import ToolRegistry
from .turn_runtime import TurnRuntimeState


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
    hook_runner: HookRunner | None = None
    system_prompt: str = ""
    conversation: ConversationState = field(default_factory=ConversationState)
    turn_runtime: TurnRuntimeState = field(default_factory=TurnRuntimeState)
    _client: AsyncOpenAI | None = field(default=None, repr=False)
    tool_orchestrator: ToolOrchestrator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.tool_orchestrator = ToolOrchestrator(
            bus=self.bus,
            registry=self.registry,
            permission_checker=self.permission_checker,
            hook_runner=self.hook_runner,
            status_callback=self.turn_runtime.mark_tool_status,
        )

    @property
    def messages(self) -> list[ChatMessage]:
        return self.conversation.messages

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
        if self.prompt_builder:
            prompt = self.prompt_builder.build()
            self.turn_runtime.set_memory_entry(self.prompt_builder.memory_entry_metadata)
        else:
            prompt = self.system_prompt
            self.turn_runtime.set_memory_entry(None)
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
                entry: dict[str, Any] = {"role": m.role, "content": m.content or ""}
                if m.reasoning_details is not None:
                    entry["reasoning_details"] = m.reasoning_details
                msgs.append(entry)  # type: ignore[arg-type]
        return msgs

    async def handle_user_message(self, user_input: str) -> None:
        """Process a user message. Emits events via MessageBus."""
        # Hook: USER_PROMPT_SUBMIT — can block or rewrite input
        if self.hook_runner:
            agg = await self.hook_runner.run_hooks(
                HookEvent.USER_PROMPT_SUBMIT, arguments={"input": user_input},
            )
            if agg.should_block:
                await self.bus.emit(Error(message=f"Blocked by hook: {'; '.join(agg.blocking_errors)}"))
                return
            if agg.updated_input and "input" in agg.updated_input:
                user_input = agg.updated_input["input"]

        self.messages.append(ChatMessage(role="user", content=user_input))
        self._refresh_turn_runtime_metrics()
        await self.bus.emit(AgentStart())

        while True:
            self.turn_runtime.start_turn(model_id=self.config.model_id)
            await self.bus.emit(TurnStart())

            # Build API kwargs dynamically to avoid NOT_GIVEN sentinel issues
            create_kwargs: dict[str, Any] = {
                "model": self.config.model_id,
                "messages": self._build_messages(),
                "stream": True,
            }

            tools_param = self.registry.to_openai_tools() if len(self.registry) > 0 else None
            if tools_param:
                create_kwargs["tools"] = tools_param
            if self.config.is_reasoning:
                create_kwargs["extra_body"] = {"reasoning": {"enabled": True}}

            stream = await self.client.chat.completions.create(**create_kwargs)

            text_chunks: list[str] = []
            reasoning_chunks: list[str] = []
            tool_calls_buf: dict[int, ToolCallInfo] = {}
            finish_reason: str | None = None

            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                delta = choice.delta

                # Capture reasoning content (OpenRouter extended field)
                reasoning_delta = getattr(delta, "reasoning", None) if delta else None
                if isinstance(reasoning_delta, str) and reasoning_delta:
                    reasoning_chunks.append(reasoning_delta)
                    self.turn_runtime.record_reasoning_delta(reasoning_delta)

                if delta and delta.content:
                    text_chunks.append(delta.content)
                    self.turn_runtime.record_text_delta(delta.content)
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
                        self.turn_runtime.set_buffered_tool_calls(
                            [tool_calls_buf[i] for i in sorted(tool_calls_buf)]
                        )

            self.turn_runtime.finish_reason = finish_reason or "stop"
            await self.bus.emit(TurnEnd(finish_reason=finish_reason or "stop"))

            if finish_reason == "tool_calls" and tool_calls_buf:
                sorted_calls = [tool_calls_buf[i] for i in sorted(tool_calls_buf)]
                self.turn_runtime.set_buffered_tool_calls(sorted_calls)
                self.turn_runtime.set_tool_queue(sorted_calls)
                self.turn_runtime.enter_tool_phase(finish_reason=finish_reason)

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
                self._refresh_turn_runtime_metrics()

                await self._execute_tool_calls(sorted_calls)
                continue

            self.messages.append(ChatMessage(
                role="assistant",
                content="".join(text_chunks),
                reasoning_details="".join(reasoning_chunks) if reasoning_chunks else None,
            ))
            self._refresh_turn_runtime_metrics()
            self.turn_runtime.complete(finish_reason=finish_reason or "stop")
            break

        # Hook: STOP — allows hooks to inspect/augment final response
        if self.hook_runner:
            final_text = self.messages[-1].content or ""
            agg = await self.hook_runner.run_hooks(
                HookEvent.STOP, result=final_text,
            )
            if agg.additional_contexts:
                ctx_text = "\n".join(agg.additional_contexts)
                self.messages.append(ChatMessage(role="system", content=f"[Hook context] {ctx_text}"))
                self._refresh_turn_runtime_metrics()

        await self.bus.emit(AgentEnd())

        # Auto-compact if approaching token limit
        if self.compactor and self.compactor.should_compact(self.messages):
            # Hook: PRE_COMPACT
            if self.hook_runner:
                await self.hook_runner.run_hooks(HookEvent.PRE_COMPACT)
            await self._auto_compact()
            # Hook: POST_COMPACT
            if self.hook_runner:
                await self.hook_runner.run_hooks(HookEvent.POST_COMPACT)

    async def _execute_tool_calls(self, tool_calls: list[ToolCallInfo]) -> None:
        """Execute tool calls through the shared orchestrator."""
        results = await self.tool_orchestrator.execute_tool_calls(tool_calls)
        for result in results:
            self.messages.append(result.to_message())
            self._refresh_turn_runtime_metrics()

    async def _run_one_tool(self, tc: ToolCallInfo) -> str:
        """Run a single tool through the shared orchestrator."""
        return (await self.tool_orchestrator.execute_tool_call(tc)).content

    async def _auto_compact(self) -> None:
        """Compact conversation when token threshold is exceeded."""
        if not self.compactor:
            return
        result = await self.compactor.compact(self.messages)
        if result.removed_count == 0:
            return
        # Replace messages: summary boundary + preserved tail
        preserved = self.messages[len(self.messages) - result.preserved_count:]
        self.conversation.clear()
        self.messages.extend(result.to_messages())
        self.messages.extend(preserved)
        self.turn_runtime.record_compaction(
            removed_count=result.removed_count,
            preserved_count=result.preserved_count,
            pre_tokens=result.pre_tokens,
            post_tokens=result.post_tokens,
            message_count=len(self.messages),
        )
        self._refresh_turn_runtime_metrics()
        # Invalidate prompt cache since context changed
        if self.prompt_builder:
            self.prompt_builder.invalidate()

    def switch_model(self, new_config: ModelConfig) -> None:
        """Switch to a different model config. Closes existing HTTP client."""
        self.config = new_config
        if self._client is not None:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._client.close())
            except RuntimeError:
                pass
            self._client = None

    def reset(self) -> None:
        self.messages.clear()
        self.turn_runtime.reset()

    def _refresh_turn_runtime_metrics(self) -> None:
        compaction_pending = False
        if self.compactor is not None:
            compaction_pending = self.compactor.should_compact(self.messages)
        self.turn_runtime.update_message_metrics(
            self.messages,
            compaction_pending=compaction_pending,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
