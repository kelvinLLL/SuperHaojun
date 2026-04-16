"""Tests for Feature 15: TUI (Rich terminal interface)."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from rich.console import Console

from superhaojun.agent import Agent
from superhaojun.bus import MessageBus
from superhaojun.commands import Command, CommandContext, CommandRegistry
from superhaojun.config import ModelConfig
from superhaojun.messages import (
    AgentEnd, AgentStart, Error,
    PermissionRequest, TextDelta,
    ToolCallEnd, ToolCallStart, TurnEnd, TurnStart,
)
from superhaojun.tui.app import TUIApp
from superhaojun.tui.renderer import TUIRenderer, _format_args, _looks_like_code


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
class TestFormatArgs:
    def test_dict(self) -> None:
        result = _format_args({"path": "/tmp/test.py", "content": "hello"})
        assert "path" in result
        assert "hello" in result

    def test_truncation(self) -> None:
        long_args = {"key": "x" * 200}
        result = _format_args(long_args, max_len=50)
        assert len(result) <= 51  # 50 + ellipsis char
        assert result.endswith("…")

    def test_non_dict(self) -> None:
        result = _format_args("simple string")
        assert result == "simple string"


class TestLooksLikeCode:
    def test_code_indicators(self) -> None:
        assert _looks_like_code("def foo():\n  pass")
        assert _looks_like_code("import os\nimport sys")
        assert _looks_like_code("class MyClass:")

    def test_multiline(self) -> None:
        text = "line1\nline2\nline3\nline4\nline5"
        assert _looks_like_code(text)

    def test_plain_text(self) -> None:
        assert not _looks_like_code("Done successfully")
        assert not _looks_like_code("No such file")


# ---------------------------------------------------------------------------
# TUIRenderer
# ---------------------------------------------------------------------------
class TestTUIRenderer:
    def _make_console(self) -> Console:
        return Console(file=StringIO(), theme=None, force_terminal=True, width=120)

    def test_register_handlers(self) -> None:
        bus = MessageBus()
        renderer = TUIRenderer(console=self._make_console())
        renderer.register(bus)
        # Verify handlers were registered for key message types
        assert "text_delta" in bus._handlers
        assert "agent_start" in bus._handlers
        assert "agent_end" in bus._handlers

    def test_text_collection(self) -> None:
        renderer = TUIRenderer(console=self._make_console())
        renderer._on_text_delta(TextDelta(text="Hello"))
        renderer._on_text_delta(TextDelta(text=" World"))
        assert renderer._text_buffer == ["Hello", " World"]

    def test_agent_start_clears_buffer(self) -> None:
        renderer = TUIRenderer(console=self._make_console())
        renderer._text_buffer = ["old text"]
        renderer._on_agent_start(AgentStart())
        assert renderer._text_buffer == []

    def test_agent_end_renders_markdown(self) -> None:
        console = self._make_console()
        renderer = TUIRenderer(console=console)
        renderer._text_buffer = ["# Hello\n\nThis is **bold** text."]
        renderer._on_agent_end(AgentEnd())
        output = console.file.getvalue()
        assert "Hello" in output

    def test_tool_call_start(self) -> None:
        console = self._make_console()
        renderer = TUIRenderer(console=console)
        renderer._on_tool_call_start(ToolCallStart(
            tool_call_id="tc1", tool_name="read_file", arguments={"path": "/tmp/test.py"},
        ))
        output = console.file.getvalue()
        assert "read_file" in output
        assert "tc1" in renderer._active_tools

    def test_tool_call_end(self) -> None:
        console = self._make_console()
        renderer = TUIRenderer(console=console)
        renderer._active_tools["tc1"] = "read_file"
        renderer._on_tool_call_end(ToolCallEnd(
            tool_call_id="tc1", tool_name="read_file", result="file contents here",
        ))
        output = console.file.getvalue()
        assert "read_file" in output
        assert "tc1" not in renderer._active_tools

    def test_tool_call_end_long_result_truncated(self) -> None:
        console = self._make_console()
        renderer = TUIRenderer(console=console)
        long_result = "x" * 300
        renderer._on_tool_call_end(ToolCallEnd(
            tool_call_id="tc1", tool_name="bash", result=long_result,
        ))
        output = console.file.getvalue()
        assert "bash" in output

    def test_tool_call_end_code_result(self) -> None:
        console = self._make_console()
        renderer = TUIRenderer(console=console)
        code_result = "def foo():\n    return 42\n\nclass Bar:\n    pass"
        renderer._on_tool_call_end(ToolCallEnd(
            tool_call_id="tc1", tool_name="read_file", result=code_result,
        ))
        output = console.file.getvalue()
        assert "read_file" in output

    def test_error(self) -> None:
        console = self._make_console()
        renderer = TUIRenderer(console=console)
        renderer._on_error(Error(message="something went wrong"))
        output = console.file.getvalue()
        assert "something went wrong" in output

    def test_print_welcome(self) -> None:
        console = self._make_console()
        renderer = TUIRenderer(console=console)
        renderer.print_welcome(
            model_id="gpt-5.4", base_url="https://example.com",
            tool_count=7, cmd_count=5,
        )
        output = console.file.getvalue()
        assert "SuperHaojun" in output
        assert "gpt-5.4" in output

    @pytest.mark.asyncio
    async def test_full_message_flow(self) -> None:
        """Test a complete flow: agent_start -> text deltas -> tool call -> agent_end."""
        bus = MessageBus()
        console = self._make_console()
        renderer = TUIRenderer(console=console)
        renderer.register(bus)

        await bus.emit(AgentStart())
        await bus.emit(TextDelta(text="I will "))
        await bus.emit(TextDelta(text="read the file."))
        await bus.emit(ToolCallStart(tool_call_id="tc1", tool_name="read_file", arguments={"path": "/tmp/test.py"}))
        await bus.emit(ToolCallEnd(tool_call_id="tc1", tool_name="read_file", result="contents"))
        await bus.emit(AgentEnd())

        output = console.file.getvalue()
        assert "read_file" in output
        assert "read the file" in output  # From markdown rendering

    def test_turn_handlers_noop(self) -> None:
        """Turn start/end handlers should not raise."""
        renderer = TUIRenderer(console=self._make_console())
        renderer._on_turn_start(TurnStart())
        renderer._on_turn_end(TurnEnd(finish_reason="stop"))


class _SpyCommand(Command):
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    @property
    def name(self) -> str:
        return "spy"

    @property
    def description(self) -> str:
        return "Spy command"

    async def execute(self, args: str, context: CommandContext) -> str | None:
        self.calls.append((args, context))
        return None


class TestTUIApp:
    def _make_console(self) -> Console:
        return Console(file=StringIO(), theme=None, force_terminal=True, width=120)

    def _make_agent(self) -> Agent:
        return Agent(
            config=ModelConfig(
                provider="openai",
                model_id="gpt-4o",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
            ),
            bus=MessageBus(),
        )

    @pytest.mark.asyncio
    async def test_command_execute_receives_args_before_context(self, tmp_path: Path) -> None:
        spy = _SpyCommand()
        registry = CommandRegistry()
        registry.register(spy)

        app = TUIApp(
            agent=self._make_agent(),
            cmd_registry=registry,
            console=self._make_console(),
            history_file=str(tmp_path / "history.txt"),
        )
        app._get_input = AsyncMock(side_effect=["/spy hello world", EOFError()])

        await app.run()

        assert spy.calls
        assert spy.calls[0][0] == "hello world"
        assert isinstance(spy.calls[0][1], CommandContext)

    @pytest.mark.asyncio
    async def test_uses_provided_command_context(self, tmp_path: Path) -> None:
        spy = _SpyCommand()
        registry = CommandRegistry()
        registry.register(spy)
        agent = self._make_agent()
        context = CommandContext(agent=agent)

        app = TUIApp(
            agent=agent,
            cmd_registry=registry,
            console=self._make_console(),
            history_file=str(tmp_path / "history.txt"),
            command_context=context,
        )
        app._get_input = AsyncMock(side_effect=["/spy hi", EOFError()])

        await app.run()

        assert spy.calls
        assert spy.calls[0][1] is context


class TestTUILauncher:
    @pytest.mark.asyncio
    async def test_run_tui_uses_runtime_lifecycle(self) -> None:
        from superhaojun.tui.launcher import run_tui

        runtime = MagicMock()
        runtime.startup = AsyncMock()
        runtime.shutdown = AsyncMock()
        runtime.agent = MagicMock()
        runtime.command_registry = MagicMock()
        runtime.build_command_context.return_value = CommandContext(agent=runtime.agent)

        app = MagicMock()
        app.run = AsyncMock()

        with patch("superhaojun.tui.launcher.TUIApp", return_value=app) as tui_app_cls:
            await run_tui(runtime)

        runtime.startup.assert_awaited_once()
        runtime.shutdown.assert_awaited_once()
        runtime.build_command_context.assert_called_once_with()
        tui_app_cls.assert_called_once()
        app.run.assert_awaited_once()
