"""Tests for command system."""

from __future__ import annotations

from pathlib import Path

import pytest

from superhaojun.agent import Agent
from superhaojun.bus import MessageBus
from superhaojun.commands import (
    Command, CommandContext, CommandRegistry,
    register_builtin_commands,
)
from superhaojun.commands.builtins import (
    ClearCommand, HelpCommand, MessagesCommand,
    MemoryCommand, ModelCommand, QuitCommand, ToolsCommand, ExtensionsCommand,
)
from superhaojun.config import ModelConfig
from superhaojun.memory.store import MemoryCategory, MemoryStore
from superhaojun.prompt.builder import SystemPromptBuilder
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
        assert len(cmd_registry) == 12  # help, clear, compact, quit, exit, memory, messages, model, session, tools, extensions, mcp
        assert cmd_registry.get("mcp") is not None
        assert cmd_registry.get("extensions") is not None


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

    async def test_memory_add_refreshes_prompt_memory_entry(self, tmp_path: Path, agent: Agent) -> None:
        memory_store = MemoryStore(storage_dir=tmp_path / "memory")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        agent.prompt_builder = builder
        builder.set_memory_text("")

        ctx = CommandContext(agent=agent)
        ctx.memory_store = memory_store  # type: ignore[attr-defined]

        result = await MemoryCommand().execute("add user Prefers careful refactors", ctx)

        assert "Memory added" in result
        assert "Prefers careful refactors" in builder.build()
        assert builder.memory_entry_metadata is not None
        assert builder.memory_entry_metadata["loaded_entries"]

    async def test_memory_delete_refreshes_prompt_memory_entry(self, tmp_path: Path, agent: Agent) -> None:
        memory_store = MemoryStore(storage_dir=tmp_path / "memory")
        real_entry = memory_store.add(MemoryCategory.USER, "Keeps notes short")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        agent.prompt_builder = builder
        builder.set_memory_entry(memory_store.build_prompt_entry())

        ctx = CommandContext(agent=agent)
        ctx.memory_store = memory_store  # type: ignore[attr-defined]

        result = await MemoryCommand().execute(f"delete {real_entry.entry_id}", ctx)

        assert result == "Memory deleted."
        assert builder.memory_entry_metadata is None or builder.memory_entry_metadata["loaded_entries"] == []

    async def test_extensions_list_and_disable_refresh_prompt(self, tmp_path: Path, agent: Agent) -> None:
        from superhaojun.extensions.runtime import ExtensionRuntime

        (tmp_path / "SUPERHAOJUN.md").write_text("Use dataclasses.", encoding="utf-8")
        brand = tmp_path / ".haojun"
        brand.mkdir()

        runtime = ExtensionRuntime(working_dir=tmp_path, config_path=brand / "extensions.json")
        builder = SystemPromptBuilder(working_dir=str(tmp_path), extension_runtime=runtime)
        agent.prompt_builder = builder

        ctx = CommandContext(agent=agent)
        ctx.extension_runtime = runtime  # type: ignore[attr-defined]

        listed = await ExtensionsCommand().execute("", ctx)
        extension_id = runtime.list_extensions()[0]["id"]
        assert "Use dataclasses." in builder.build()
        disabled = await ExtensionsCommand().execute(f"disable {extension_id}", ctx)

        assert "SUPERHAOJUN.md" in listed
        assert "disabled" in disabled.lower()
        assert "Use dataclasses." not in builder.build()
