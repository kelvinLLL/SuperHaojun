"""TUI App — full terminal application with prompt_toolkit input and rich output.

Replaces the simple REPL loop in main.py with a rich TUI experience.
Uses prompt_toolkit for input (history, completion, multi-line) and
rich for output (Markdown, panels, syntax highlights).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML

from rich.console import Console

from ..agent import Agent
from ..commands import CommandContext, CommandRegistry
from ..constants import BRAND_DIR
from ..runtime import build_command_context
from .renderer import TUIRenderer, THEME


class TUIApp:
    """Full terminal application combining prompt_toolkit + rich.

    Features:
    - Input history with file persistence
    - Auto-suggest from history
    - Rich Markdown rendering of agent responses
    - Styled tool execution display
    - Ctrl+C handling (cancels current, doesn't exit)

    Usage:
        app = TUIApp(agent=agent, cmd_registry=cmd_registry)
        await app.run()
    """

    def __init__(
        self,
        agent: Agent,
        cmd_registry: CommandRegistry,
        console: Console | None = None,
        history_file: str | None = None,
        command_context: CommandContext | None = None,
    ) -> None:
        self.agent = agent
        self.cmd_registry = cmd_registry
        self.console = console or Console(theme=THEME)
        self.renderer = TUIRenderer(console=self.console)
        self.renderer.register(agent.bus)
        self.command_context = command_context

        # Input session with history
        hf = history_file or str(Path.home() / BRAND_DIR / "input_history")
        self._session: PromptSession[str] = PromptSession(
            history=FileHistory(hf),
            auto_suggest=AutoSuggestFromHistory(),
            multiline=False,
        )
        self._running = True

    def _command_context(self) -> CommandContext:
        if self.command_context is not None:
            return self.command_context
        return build_command_context(
            self.agent,
            command_registry=self.cmd_registry,
        )

    async def run(self) -> None:
        """Main REPL loop with rich rendering."""
        self.renderer.print_welcome(
            model_id=self.agent.config.model_id,
            base_url=self.agent.config.base_url,
            tool_count=len(self.agent.registry),
            cmd_count=len(self.cmd_registry),
        )

        while self._running:
            try:
                user_input = await self._get_input()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]Goodbye![/dim]")
                break

            text = user_input.strip()
            if not text:
                continue

            # Command handling
            if text.startswith("/"):
                parts = text.split(maxsplit=1)
                cmd_name = parts[0][1:]  # strip leading /
                cmd_args = parts[1] if len(parts) > 1 else ""

                if cmd_name in ("quit", "exit", "q"):
                    self.console.print("[dim]Goodbye![/dim]")
                    break

                cmd = self.cmd_registry.get(cmd_name)
                if cmd:
                    result = await cmd.execute(cmd_args, self._command_context())
                    if result:
                        self.console.print(result)
                else:
                    self.console.print(f"[warning]Unknown command: /{cmd_name}[/warning]")
                continue

            # Agent conversation
            try:
                await self.agent.handle_user_message(text)
            except KeyboardInterrupt:
                self.console.print("\n[warning]Interrupted[/warning]")
            except Exception as exc:
                self.console.print(f"[error]Error: {exc}[/error]")

    async def _get_input(self) -> str:
        """Get user input via prompt_toolkit (async)."""
        return await self._session.prompt_async(
            HTML("<cyan><b>❯ </b></cyan>"),
        )

    def stop(self) -> None:
        """Signal the REPL to stop."""
        self._running = False
