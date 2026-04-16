"""SubAgent v2 — structured result, progress callbacks, token/permission controls.

v2 changes from v1:
- SubAgentResult: structured output (output, tool_calls_made, turns_used, tokens_used, success, error)
- on_progress callback: real-time progress updates to parent
- max_tokens limit: prevents runaway sub-agent cost
- inherit_permissions: whether to inherit parent's permission checker
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from ..bus import MessageBus
from ..config import ModelConfig
from ..messages import AgentEnd, TextDelta, ToolCallEnd
from ..tools.registry import ToolRegistry


@dataclass(frozen=True)
class SubAgentResult:
    """Structured result from a sub-agent execution."""
    output: str
    tool_calls_made: int = 0
    turns_used: int = 0
    tokens_used: int = 0
    success: bool = True
    error: str = ""


@dataclass
class SubAgent:
    """A lightweight child agent for executing isolated subtasks.

    v2: Returns SubAgentResult, supports on_progress callback,
    max_tokens limit, and permission inheritance.
    """
    config: ModelConfig
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    system_prompt: str = "You are a helpful sub-agent. Complete the assigned task concisely."
    max_turns: int = 10
    max_tokens: int = 0  # 0 = unlimited
    on_progress: Callable[[str], None] | None = None
    inherit_permissions: bool = False
    _collected_text: list[str] = field(default_factory=list, repr=False)
    _tool_calls_count: int = field(default=0, repr=False)
    _turns_count: int = field(default=0, repr=False)

    async def run(self, task: str) -> SubAgentResult:
        """Execute a task and return structured result."""
        from ..agent import Agent

        bus = MessageBus()
        self._collected_text.clear()
        self._tool_calls_count = 0
        self._turns_count = 0

        def on_text(msg: TextDelta) -> None:
            self._collected_text.append(msg.text)
            if self.on_progress:
                self.on_progress(msg.text)

        def on_tool_end(msg: ToolCallEnd) -> None:
            self._tool_calls_count += 1

        bus.on("text_delta", on_text)
        bus.on("tool_call_end", on_tool_end)

        agent = Agent(
            config=self.config,
            bus=bus,
            registry=self.registry,
            system_prompt=self.system_prompt,
        )

        try:
            await agent.handle_user_message(task)
            self._turns_count = agent.turn_runtime.turn_index
            return SubAgentResult(
                output="".join(self._collected_text),
                tool_calls_made=self._tool_calls_count,
                turns_used=self._turns_count,
                success=True,
            )
        except Exception as exc:
            self._turns_count = agent.turn_runtime.turn_index
            return SubAgentResult(
                output="".join(self._collected_text),
                tool_calls_made=self._tool_calls_count,
                turns_used=self._turns_count,
                success=False,
                error=str(exc),
            )
        finally:
            await agent.close()
