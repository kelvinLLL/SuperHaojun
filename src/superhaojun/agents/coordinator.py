"""Coordinator — distributes tasks across multiple SubAgents.

The Coordinator pattern allows the main agent to break down a complex
request into multiple subtasks, execute them in parallel via SubAgents,
and aggregate results.

Reference: Claude Code's Coordinator / Swarm pattern.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..config import ModelConfig
from ..tools.registry import ToolRegistry
from .sub_agent import SubAgent


@dataclass(frozen=True)
class TaskSpec:
    """Specification for a single subtask.

    Attributes:
        task_id: Unique identifier for this task.
        description: Task description for the SubAgent.
        system_prompt: Optional custom system prompt (overrides default).
    """
    task_id: str
    description: str
    system_prompt: str = ""


@dataclass(frozen=True)
class TaskResult:
    """Result of a single subtask execution.

    Attributes:
        task_id: Matches the TaskSpec.task_id.
        output: Text output from the SubAgent.
        success: Whether the task completed without error.
    """
    task_id: str
    output: str
    success: bool = True


@dataclass
class Coordinator:
    """Distributes tasks across parallel SubAgents and collects results.

    Usage:
        coord = Coordinator(config=config, registry=registry)
        tasks = [
            TaskSpec("t1", "Analyze src/agent.py"),
            TaskSpec("t2", "Analyze src/bus.py"),
            TaskSpec("t3", "Summarize test coverage"),
        ]
        results = await coord.run(tasks)
        for r in results:
            print(f"{r.task_id}: {r.output[:100]}")
    """
    config: ModelConfig
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    default_system_prompt: str = "You are a helpful sub-agent. Complete the assigned task concisely."
    max_concurrent: int = 5
    max_turns_per_task: int = 10

    async def run(self, tasks: list[TaskSpec]) -> list[TaskResult]:
        """Execute all tasks, respecting max_concurrent limit.

        Tasks are run in parallel batches. Results are returned in
        the same order as the input tasks.
        """
        if not tasks:
            return []

        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def bounded_run(spec: TaskSpec) -> TaskResult:
            async with semaphore:
                return await self._run_one(spec)

        results = await asyncio.gather(
            *(bounded_run(spec) for spec in tasks),
            return_exceptions=True,
        )

        task_results: list[TaskResult] = []
        for spec, result in zip(tasks, results):
            if isinstance(result, BaseException):
                task_results.append(TaskResult(
                    task_id=spec.task_id,
                    output=f"Error: {result}",
                    success=False,
                ))
            else:
                task_results.append(result)
        return task_results

    async def run_sequential(self, tasks: list[TaskSpec]) -> list[TaskResult]:
        """Execute tasks one by one (for ordered dependencies)."""
        results: list[TaskResult] = []
        for spec in tasks:
            results.append(await self._run_one(spec))
        return results

    async def _run_one(self, spec: TaskSpec) -> TaskResult:
        """Execute a single task via SubAgent."""
        system_prompt = spec.system_prompt or self.default_system_prompt
        sub = SubAgent(
            config=self.config,
            registry=self.registry,
            system_prompt=system_prompt,
            max_turns=self.max_turns_per_task,
        )
        try:
            output = await sub.run(spec.description)
            return TaskResult(task_id=spec.task_id, output=output, success=True)
        except Exception as exc:
            return TaskResult(task_id=spec.task_id, output=f"Error: {exc}", success=False)
