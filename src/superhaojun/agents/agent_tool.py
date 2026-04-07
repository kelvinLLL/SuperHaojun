"""AgentTool — a Tool that spawns a SubAgent to handle complex subtasks.

This is the main agent's interface to multi-agent: when the LLM calls
this tool, it forks a SubAgent to work on the specified task independently.

Reference: Claude Code's AgentTool in tools/ — spawns task-scoped agents.
"""

from __future__ import annotations

from typing import Any

from ..config import ModelConfig
from ..tools.base import Tool
from ..tools.registry import ToolRegistry
from .sub_agent import SubAgent


class AgentTool(Tool):
    """Tool that delegates a subtask to a SubAgent.

    The main agent can call this tool to fork an isolated child agent
    that works on a specific task without polluting the main conversation.
    """

    def __init__(
        self,
        config: ModelConfig,
        registry: ToolRegistry,
        system_prompt: str = "You are a helpful sub-agent. Complete the assigned task concisely and return the result.",
        max_turns: int = 10,
    ) -> None:
        self._config = config
        self._registry = registry
        self._system_prompt = system_prompt
        self._max_turns = max_turns

    @property
    def name(self) -> str:
        return "agent"

    @property
    def description(self) -> str:
        return (
            "Delegate a subtask to an independent sub-agent. "
            "Use this for complex, self-contained tasks that benefit from "
            "isolated context (e.g., 'analyze all test files and summarize coverage'). "
            "The sub-agent has access to the same tools but maintains its own conversation."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task description for the sub-agent to complete",
                },
            },
            "required": ["task"],
        }

    @property
    def is_concurrent_safe(self) -> bool:
        return True  # SubAgents are independent

    @property
    def risk_level(self) -> str:
        return "read"  # SubAgent inherits tool permissions

    async def execute(self, **kwargs: Any) -> str:
        task = kwargs.get("task", "")
        if not task:
            return "Error: task parameter is required"

        sub = SubAgent(
            config=self._config,
            registry=self._registry,
            system_prompt=self._system_prompt,
            max_turns=self._max_turns,
        )
        result = await sub.run(task)
        if result.success:
            return result.output
        return f"SubAgent error: {result.error}\n{result.output}"
