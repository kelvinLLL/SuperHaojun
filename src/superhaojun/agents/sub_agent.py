"""SubAgent — a child agent that runs in isolation with its own MessageBus.

SubAgents share the same ModelConfig and ToolRegistry as the parent,
but have their own conversation history and MessageBus. They execute
a single task and return the result.

Reference: Claude Code's AgentTool — forks a task-scoped agent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..bus import MessageBus
from ..config import ModelConfig
from ..messages import AgentEnd, TextDelta
from ..tools.registry import ToolRegistry


@dataclass
class SubAgent:
    """A lightweight child agent for executing isolated subtasks.

    Unlike the main Agent, a SubAgent:
    - Has its own MessageBus (no cross-talk with parent)
    - Collects text output internally (no terminal rendering)
    - Runs a single task and returns the text result
    - Shares config + tools with parent (no re-initialization)

    Usage:
        sub = SubAgent(config=parent.config, registry=parent.registry)
        result = await sub.run("Analyze this code and list all functions")
    """
    config: ModelConfig
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    system_prompt: str = "You are a helpful sub-agent. Complete the assigned task concisely."
    max_turns: int = 10
    _collected_text: list[str] = field(default_factory=list, repr=False)

    async def run(self, task: str) -> str:
        """Execute a task and return the collected text output.

        Creates a temporary Agent + MessageBus, processes the task,
        and returns all text deltas concatenated.
        """
        # Lazy import to avoid circular dependency
        from ..agent import Agent

        bus = MessageBus()
        self._collected_text.clear()

        # Collect text output
        def on_text(msg: TextDelta) -> None:
            self._collected_text.append(msg.text)

        bus.on("text_delta", on_text)

        agent = Agent(
            config=self.config,
            bus=bus,
            registry=self.registry,
            system_prompt=self.system_prompt,
        )

        try:
            await agent.handle_user_message(task)
        except Exception as exc:
            return f"SubAgent error: {exc}"
        finally:
            await agent.close()

        return "".join(self._collected_text)
