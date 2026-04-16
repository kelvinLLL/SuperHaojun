"""CLI entry point: async REPL with message-driven architecture.

The REPL registers handlers on the MessageBus for rendering outbound messages
and sending inbound messages (user input, permission responses).
"""

from __future__ import annotations

import asyncio
import os
import sys

from .bus import MessageBus
from .messages import (
    AgentEnd, AgentStart, Error,
    PermissionRequest, PermissionResponse,
    TextDelta, ToolCallEnd, ToolCallStart,
)
from .runtime import AppRuntime, build_runtime

CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
DIM = "\033[2m"
RED = "\033[31m"
RESET = "\033[0m"


def _register_render_handlers(bus: MessageBus) -> None:
    """Register handlers that render outbound messages to the terminal."""

    def on_text_delta(msg: TextDelta) -> None:
        sys.stdout.write(msg.text)
        sys.stdout.flush()

    def on_tool_call_start(msg: ToolCallStart) -> None:
        sys.stdout.write(f"\n{DIM}⚙ {msg.tool_name}({msg.arguments}){RESET}\n")
        sys.stdout.flush()

    def on_tool_call_end(msg: ToolCallEnd) -> None:
        preview = msg.result[:200] + "..." if len(msg.result) > 200 else msg.result
        sys.stdout.write(f"{DIM}✓ {msg.tool_name} → {preview}{RESET}\n\n")
        sys.stdout.flush()

    def on_error(msg: Error) -> None:
        sys.stdout.write(f"{RED}Error: {msg.message}{RESET}\n")
        sys.stdout.flush()

    def on_agent_start(msg: AgentStart) -> None:
        sys.stdout.write(CYAN)
        sys.stdout.flush()

    def on_agent_end(msg: AgentEnd) -> None:
        sys.stdout.write(f"{RESET}\n\n")
        sys.stdout.flush()

    async def on_permission_request(msg: PermissionRequest) -> None:
        sys.stdout.write(
            f"\n{YELLOW}⚠ {msg.tool_name} requires permission "
            f"(risk: {msg.risk_level}){RESET}\n"
        )
        sys.stdout.write(f"{DIM}  args: {msg.arguments}{RESET}\n")
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(
            None, lambda: input(f"{YELLOW}Allow? [y/n]: {RESET}")
        )
        granted = answer.strip().lower() in ("y", "yes")
        await bus.emit(PermissionResponse(
            tool_call_id=msg.tool_call_id, granted=granted,
        ))

    bus.on("text_delta", on_text_delta)
    bus.on("tool_call_start", on_tool_call_start)
    bus.on("tool_call_end", on_tool_call_end)
    bus.on("error", on_error)
    bus.on("agent_start", on_agent_start)
    bus.on("agent_end", on_agent_end)
    bus.on("permission_request", on_permission_request)


async def repl(runtime: AppRuntime) -> None:
    loop = asyncio.get_event_loop()
    agent = runtime.agent
    cmd_registry = runtime.command_registry

    print(f"\n🤖 SuperHaojun Agent")
    print(f"   Model: {agent.config.model_id} @ {agent.config.base_url}")
    print(f"   Tools: {len(agent.registry)} | Commands: {len(cmd_registry)}")
    print(f"   Type /help for commands. Ctrl+C to exit.\n")

    while True:
        try:
            user_input: str = await loop.run_in_executor(
                None, lambda: input(f"{YELLOW}you>{RESET} ")
            )
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        trimmed = user_input.strip()
        if not trimmed:
            continue

        # Slash command dispatch
        if trimmed.startswith("/"):
            parts = trimmed[1:].split(None, 1)
            cmd_name = parts[0] if parts else ""
            cmd_args = parts[1] if len(parts) > 1 else ""

            cmd = cmd_registry.get(cmd_name)
            if cmd is None:
                matches = cmd_registry.completions(cmd_name)
                if matches:
                    print(f"Did you mean: {', '.join('/' + m for m in matches)}")
                else:
                    print(f"Unknown command: /{cmd_name}. Type /help.")
                continue

            cmd_ctx = runtime.build_command_context()
            output = await cmd.execute(cmd_args, cmd_ctx)
            if output:
                print(output)
            if cmd_ctx.should_exit:
                break
            print()
            continue

        # Regular chat — agent emits to bus, handlers render
        try:
            await agent.handle_user_message(trimmed)
        except Exception as exc:
            sys.stdout.write(f"{RESET}\n{RED}Error: {exc}{RESET}\n\n")


def main() -> None:
    runtime = build_runtime(working_dir=os.getcwd())
    _register_render_handlers(runtime.bus)
    try:
        asyncio.run(runtime.startup())
        asyncio.run(repl(runtime))
    finally:
        asyncio.run(runtime.shutdown())
