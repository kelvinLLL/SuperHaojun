"""Agents slash command — /agents list|run."""

from __future__ import annotations

from ..commands.base import Command, CommandContext


class AgentsCommand(Command):
    @property
    def name(self) -> str:
        return "agents"

    @property
    def description(self) -> str:
        return "Multi-agent operations: /agents list | /agents run <goal>"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        coordinator = getattr(context, "coordinator", None)

        parts = args.strip().split(None, 1)
        subcmd = parts[0] if parts else "list"
        target = parts[1].strip() if len(parts) > 1 else ""

        if subcmd == "list":
            if not coordinator:
                return "No coordinator configured."
            return (
                f"Coordinator: max_concurrent={coordinator.max_concurrent}, "
                f"max_turns={coordinator.max_turns_per_task}"
            )

        if subcmd == "run":
            if not coordinator:
                return "No coordinator configured."
            if not target:
                return "Usage: /agents run <goal description>"
            results = await coordinator.run_with_llm_planning(target)
            lines = [f"Completed {len(results)} subtasks:"]
            for r in results:
                status = "✓" if r.success else "✗"
                preview = r.output[:100] + "..." if len(r.output) > 100 else r.output
                lines.append(f"  {status} {r.task_id}: {preview}")
            return "\n".join(lines)

        return f"Unknown subcommand: {subcmd}. Use: list, run"
