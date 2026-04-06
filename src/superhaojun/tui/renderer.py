"""TUI Renderer — renders agent messages to styled terminal output via rich.

Replaces the plain ANSI-escape handlers in main.py with rich-powered
rendering: Markdown, syntax highlighting, panels, trees, and spinners.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, Generator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.text import Text
from rich.theme import Theme

from ..bus import MessageBus
from ..messages import (
    AgentEnd, AgentStart, Error,
    PermissionRequest, PermissionResponse,
    TextDelta, ToolCallEnd, ToolCallStart,
    TurnEnd, TurnStart,
)

THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "dim": "dim",
    "tool": "magenta",
    "prompt": "bold cyan",
})


class TUIRenderer:
    """Rich-based message renderer for the MessageBus.

    Collects TextDelta chunks and renders them as Markdown on AgentEnd.
    Shows tool execution in styled panels with spinners.

    Usage:
        console = Console()
        renderer = TUIRenderer(console=console)
        renderer.register(bus)
        # ... agent runs ...
    """

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(theme=THEME)
        self._text_buffer: list[str] = []
        self._active_tools: dict[str, str] = {}  # tool_call_id -> tool_name
        self._spinner: Spinner | None = None

    def register(self, bus: MessageBus) -> None:
        """Register render handlers on the MessageBus."""
        bus.on("agent_start", self._on_agent_start)
        bus.on("agent_end", self._on_agent_end)
        bus.on("text_delta", self._on_text_delta)
        bus.on("tool_call_start", self._on_tool_call_start)
        bus.on("tool_call_end", self._on_tool_call_end)
        bus.on("error", self._on_error)
        bus.on("turn_start", self._on_turn_start)
        bus.on("turn_end", self._on_turn_end)
        bus.on("permission_request", self._on_permission_request)

    def _on_agent_start(self, msg: AgentStart) -> None:
        self._text_buffer.clear()

    def _on_agent_end(self, msg: AgentEnd) -> None:
        full_text = "".join(self._text_buffer).strip()
        if full_text:
            md = Markdown(full_text)
            self.console.print(md)
        self.console.print()

    def _on_text_delta(self, msg: TextDelta) -> None:
        self._text_buffer.append(msg.text)

    def _on_tool_call_start(self, msg: ToolCallStart) -> None:
        self._active_tools[msg.tool_call_id] = msg.tool_name
        # Compact display: tool name + truncated args
        args_str = _format_args(msg.arguments, max_len=80)
        self.console.print(
            Text.assemble(
                ("⚙ ", "tool"),
                (msg.tool_name, "bold tool"),
                ("(", "dim"),
                (args_str, "dim"),
                (")", "dim"),
            )
        )

    def _on_tool_call_end(self, msg: ToolCallEnd) -> None:
        self._active_tools.pop(msg.tool_call_id, None)
        preview = msg.result[:150] + "…" if len(msg.result) > 150 else msg.result
        # If it looks like code, render as syntax; otherwise as text
        if _looks_like_code(preview):
            self.console.print(Panel(
                Syntax(preview, "text", theme="monokai", line_numbers=False),
                title=f"✓ {msg.tool_name}",
                border_style="green",
                expand=False,
            ))
        else:
            self.console.print(
                Text.assemble(
                    ("✓ ", "success"),
                    (msg.tool_name, "bold"),
                    (" → ", "dim"),
                    (preview, ""),
                )
            )

    def _on_error(self, msg: Error) -> None:
        self.console.print(f"[error]✗ Error: {msg.message}[/error]")

    def _on_turn_start(self, msg: TurnStart) -> None:
        pass  # Could show a spinner here

    def _on_turn_end(self, msg: TurnEnd) -> None:
        pass

    async def _on_permission_request(self, msg: PermissionRequest) -> None:
        """Show permission prompt and emit response."""
        self.console.print()
        self.console.print(Panel(
            Text.assemble(
                ("Tool: ", "bold"),
                (msg.tool_name, "tool"),
                ("\nRisk: ", "bold"),
                (msg.risk_level, "warning"),
                ("\nArgs: ", "bold"),
                (str(msg.arguments), "dim"),
            ),
            title="⚠ Permission Required",
            border_style="yellow",
        ))
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(
            None, lambda: self.console.input("[yellow]Allow? [y/n]: [/yellow]")
        )
        granted = answer.strip().lower() in ("y", "yes")
        return PermissionResponse(tool_call_id=msg.tool_call_id, granted=granted)

    def print_welcome(self, model_id: str, base_url: str, tool_count: int, cmd_count: int) -> None:
        """Print styled welcome banner."""
        self.console.print(Panel(
            Text.assemble(
                ("🤖 SuperHaojun Agent\n", "bold cyan"),
                (f"   Model: {model_id} @ {base_url}\n", ""),
                (f"   Tools: {tool_count} | Commands: {cmd_count}\n", "dim"),
                ("   Type /help for commands, /quit to exit", "dim"),
            ),
            border_style="cyan",
            expand=False,
        ))

    def print_user_prompt(self) -> str:
        """Show the input prompt. Returns user input."""
        return self.console.input("[bold cyan]❯ [/bold cyan]")


def _format_args(args: dict[str, Any] | Any, max_len: int = 80) -> str:
    """Format tool arguments for compact display."""
    if not isinstance(args, dict):
        s = str(args)
    else:
        parts = [f"{k}={repr(v)}" for k, v in args.items()]
        s = ", ".join(parts)
    return s[:max_len] + "…" if len(s) > max_len else s


def _looks_like_code(text: str) -> bool:
    """Heuristic: does this text look like code output?"""
    indicators = ["def ", "class ", "import ", "function ", "const ", "let ", "var "]
    return any(ind in text for ind in indicators) or text.count("\n") > 3
