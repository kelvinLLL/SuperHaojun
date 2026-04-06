"""Tests for command system."""

from __future__ import annotations

import pytest

from superhaojun.agent import Agent
from superhaojun.bus import MessageBus
from superhaojun.commands import (
    Command, CommandContext, CommandRegistry,
    register_builtin_commands,
)
from superhaojun.commands.builtins import (
    ClearCommand, HelpCommand, MessagesCommand,
    ModelCommand, QuitCommand, ToolsCommand,
)
from superhaojun.config import ModelConfig
from superhaojun.tools import ToolRegistry, register_builtin_tools


@pytest.fixture
def config() -> ModelConfig:
    return ModelConfig(
        provider="openai", model_id="gpt-4o",
        base_url="https://api.openai.com/v1", api_key="sk-test",
    )


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus()


@pytest.fixture
def agent(config: ModelConfig, bus: MessageBus) -> Agent:
    reg = ToolRegistry()
    register_builtin_tools(reg)
    return Agent(config=config, bus=bus, registry=reg)


@pytest.fixture
def cmd_registry() -> CommandRegistry:
    reg = CommandRegistry()
    register_builtin_commands(reg)
    return reg


@pytest.fixture
def ctx(agent: Agent, cmd_registry: CommandRegistry) -> CommandContext:
    c = CommandContext(agent=agent)
    c.command_registry = cmd_registry  # type: ignore[attr-defined]
    return c


class TestCommandABC:
    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            Command()  # type: ignore[abstract]


class TestCommandRegistry:
    def test_register_and_get(self, cmd_registry: CommandRegistry) -> None:
        assert cmd_registry.get("help") is not None
        assert cmd_registry.get("clear") is not None
        assert cmd_registry.get("quit") is not None

    def test_get_missing(self, cmd_registry: CommandRegistry) -> None:
        assert cmd_registry.get("nonexistent") is None

    def test_completions(self, cmd_registry: CommandRegistry) -> None:
        matches = cmd_registry.completions("he")
        assert "help" in matches

    def test_completions_empty_prefix(self, cmd_registry: CommandRegistry) -> None:
        matches = cmd_registry.completions("")
        assert len(matches) == len(cmd_registry)

    def test_register_builtin_count(self, cmd_registry: CommandRegistry) -> None:
        assert len(cmd_registry) == 10  # help, clear, compact, quit, exit, memory, messages, model, session, tools


class TestBuiltinCommands:
    async def test_help(self, ctx: CommandContext, cmd_registry: CommandRegistry) -> None:
        cmd = cmd_registry.get("help")
        result = await cmd.execute("", ctx)
        assert "Available commands:" in result
        assert "/help" in result
        assert "/clear" in result

    async def test_clear(self, ctx: CommandContext, cmd_registry: CommandRegistry) -> None:
        agent: Agent = ctx.agent  # type: ignore[assignment]
        from superhaojun.agent import ChatMessage
        agent.messages.append(ChatMessage(role="user", content="test"))
        assert len(agent.messages) == 1

        cmd = cmd_registry.get("clear")
        result = await cmd.execute("", ctx)
        assert "Conversation cleared" in result
        assert len(agent.messages) == 0

    async def test_quit(self, ctx: CommandContext, cmd_registry: CommandRegistry) -> None:
        cmd = cmd_registry.get("quit")
        result = await cmd.execute("", ctx)
        assert "Bye" in result
        assert ctx.should_exit is True

    async def test_exit(self, ctx: CommandContext, cmd_registry: CommandRegistry) -> None:
        cmd = cmd_registry.get("exit")
        result = await cmd.execute("", ctx)
        assert ctx.should_exit is True

    async def test_messages(self, ctx: CommandContext, cmd_registry: CommandRegistry) -> None:
        cmd = cmd_registry.get("messages")
        result = await cmd.execute("", ctx)
        assert "Messages in context: 0" in result

    async def test_model(self, ctx: CommandContext, cmd_registry: CommandRegistry) -> None:
        cmd = cmd_registry.get("model")
        result = await cmd.execute("", ctx)
        assert "gpt-4o" in result

    async def test_tools(self, ctx: CommandContext, cmd_registry: CommandRegistry) -> None:
        cmd = cmd_registry.get("tools")
        result = await cmd.execute("", ctx)
        assert "Registered tools:" in result
        assert "read_file" in result
        assert "bash" in result
