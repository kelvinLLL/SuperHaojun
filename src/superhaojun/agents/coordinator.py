"""Coordinator v2 — task distribution with LLM planning.

v2 changes from v1:
- run_with_llm_planning(): auto task decomposition via LLM
- TaskResult uses SubAgentResult internally
- Enhanced error handling and progress tracking
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from ..config import ModelConfig
from ..tools.registry import ToolRegistry
from .sub_agent import SubAgent, SubAgentResult


@dataclass(frozen=True)
class TaskSpec:
    """Specification for a single subtask."""
    task_id: str
    description: str
    system_prompt: str = ""


@dataclass(frozen=True)
class TaskResult:
    """Result of a single subtask execution."""
    task_id: str
    output: str
    success: bool = True
    tool_calls_made: int = 0
    turns_used: int = 0

    @classmethod
    def from_sub_result(cls, task_id: str, sub: SubAgentResult) -> TaskResult:
        return cls(
            task_id=task_id,
            output=sub.output if sub.success else f"Error: {sub.error}\n{sub.output}",
            success=sub.success,
            tool_calls_made=sub.tool_calls_made,
            turns_used=sub.turns_used,
        )


@dataclass
class Coordinator:
    """Distributes tasks across parallel SubAgents and collects results."""
    config: ModelConfig
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    default_system_prompt: str = "You are a helpful sub-agent. Complete the assigned task concisely."
    max_concurrent: int = 5
    max_turns_per_task: int = 10

    async def run(self, tasks: list[TaskSpec]) -> list[TaskResult]:
        """Execute all tasks, respecting max_concurrent limit."""
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
                    task_id=spec.task_id, output=f"Error: {result}", success=False,
                ))
            else:
                task_results.append(result)
        return task_results

    async def run_sequential(self, tasks: list[TaskSpec]) -> list[TaskResult]:
        """Execute tasks one by one (for ordered dependencies)."""
        return [await self._run_one(spec) for spec in tasks]

    async def run_with_llm_planning(self, goal: str) -> list[TaskResult]:
        """Auto-decompose a goal into subtasks using LLM, then execute.

        The planning step asks the LLM to break the goal into subtasks
        returned as JSON, then executes them via run().
        """
        import httpx
        from openai import AsyncOpenAI
        from ..config import make_permissive_ssl_context

        ssl_ctx = make_permissive_ssl_context()
        http_client = httpx.AsyncClient(verify=ssl_ctx)
        client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            http_client=http_client,
        )

        planning_prompt = (
            "You are a task planner. Break down the following goal into 2-5 independent subtasks.\n"
            "Return ONLY a JSON array of objects with 'task_id' and 'description' fields.\n"
            "Example: [{\"task_id\": \"t1\", \"description\": \"Analyze X\"}, ...]\n\n"
            f"Goal: {goal}"
        )

        try:
            response = await client.chat.completions.create(
                model=self.config.model_id,
                messages=[{"role": "user", "content": planning_prompt}],
            )
            content = response.choices[0].message.content or "[]"
            # Extract JSON from response (handle markdown code blocks)
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            tasks_data = json.loads(content.strip())
            tasks = [
                TaskSpec(task_id=t["task_id"], description=t["description"])
                for t in tasks_data
                if isinstance(t, dict) and "task_id" in t and "description" in t
            ]
        except Exception as exc:
            return [TaskResult(task_id="planning", output=f"Planning failed: {exc}", success=False)]
        finally:
            await client.close()

        if not tasks:
            return [TaskResult(task_id="planning", output="No tasks generated", success=False)]

        return await self.run(tasks)

    async def _run_one(self, spec: TaskSpec) -> TaskResult:
        """Execute a single task via SubAgent."""
        sub = SubAgent(
            config=self.config,
            registry=self.registry,
            system_prompt=spec.system_prompt or self.default_system_prompt,
            max_turns=self.max_turns_per_task,
        )
        sub_result = await sub.run(spec.description)
        return TaskResult.from_sub_result(spec.task_id, sub_result)
