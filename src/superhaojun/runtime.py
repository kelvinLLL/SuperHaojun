"""Shared runtime assembly for CLI, WebUI, and other entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent import Agent
from .bus import MessageBus
from .commands import CommandContext, CommandRegistry, register_builtin_commands
from .config import ModelRegistry, load_model_registry
from .constants import BRAND_DIR
from .extensions import ExtensionRuntime
from .hooks.config import HookRegistry
from .hooks.runner import HookRunner
from .memory.store import MemoryStore
from .mcp import MCPManager, load_mcp_configs
from .prompt.builder import SystemPromptBuilder
from .session.manager import SessionManager
from .tools import ToolRegistry, register_builtin_tools


def build_command_context(agent: object, **dependencies: Any) -> CommandContext:
    """Create a CommandContext with a consistent dependency surface."""
    context = CommandContext(agent=agent)
    for key, value in dependencies.items():
        setattr(context, key, value)
    return context


@dataclass
class AppRuntime:
    """Shared runtime objects reused by multiple entrypoints."""

    working_dir: Path
    brand_root: Path
    bus: MessageBus
    agent: Agent
    tool_registry: ToolRegistry
    command_registry: CommandRegistry
    model_registry: ModelRegistry
    session_manager: SessionManager
    memory_store: MemoryStore
    extension_runtime: ExtensionRuntime
    prompt_builder: SystemPromptBuilder
    hook_registry: HookRegistry
    hook_runner: HookRunner | None
    mcp_manager: MCPManager

    def build_command_context(self) -> CommandContext:
        return build_command_context(
            self.agent,
            command_registry=self.command_registry,
            model_registry=self.model_registry,
            session_manager=self.session_manager,
            memory_store=self.memory_store,
            mcp_manager=self.mcp_manager,
            extension_runtime=self.extension_runtime,
        )

    async def startup(self) -> None:
        await self.mcp_manager.start_all()

    async def shutdown(self) -> None:
        await self.mcp_manager.stop_all()
        await self.agent.close()


def build_runtime(
    *,
    working_dir: str | Path,
    model_registry: ModelRegistry | None = None,
) -> AppRuntime:
    """Build the shared runtime dependency set for an entrypoint."""
    working_path = Path(working_dir)
    model_registry = model_registry or load_model_registry()

    bus = MessageBus()
    tool_registry = ToolRegistry()
    register_builtin_tools(tool_registry)

    command_registry = CommandRegistry()
    register_builtin_commands(command_registry)

    brand_root = working_path / BRAND_DIR
    session_manager = SessionManager(storage_dir=brand_root / "sessions")
    memory_store = MemoryStore(storage_dir=brand_root / "memory")
    extension_runtime = ExtensionRuntime(
        working_dir=working_path,
        config_path=brand_root / "extensions.json",
    )

    hook_registry = HookRegistry.load(brand_root / "hooks.json")
    hook_runner = HookRunner(
        registry=hook_registry,
        working_dir=str(working_path),
    ) if hook_registry.list_hooks() else None

    mcp_manager = MCPManager()
    mcp_manager.set_tool_registry(tool_registry)
    mcp_manager.load_configs(
        load_mcp_configs(
            project_path=brand_root / "mcp.json",
            user_path=Path.home() / BRAND_DIR / "mcp.json",
        )
    )

    tool_summaries = [
        {
            "name": tool_def["function"]["name"],
            "description": tool_def["function"].get("description", ""),
        }
        for tool_def in tool_registry.to_openai_tools()
    ]

    prompt_builder = SystemPromptBuilder(
        working_dir=str(working_path),
        tool_summaries=tool_summaries,
        extension_runtime=extension_runtime,
    )
    prompt_builder.set_memory_entry(memory_store.build_prompt_entry())

    agent = Agent(
        config=model_registry.active,
        bus=bus,
        registry=tool_registry,
        prompt_builder=prompt_builder,
        hook_runner=hook_runner,
    )

    return AppRuntime(
        working_dir=working_path,
        brand_root=brand_root,
        bus=bus,
        agent=agent,
        tool_registry=tool_registry,
        command_registry=command_registry,
        model_registry=model_registry,
        session_manager=session_manager,
        memory_store=memory_store,
        extension_runtime=extension_runtime,
        prompt_builder=prompt_builder,
        hook_registry=hook_registry,
        hook_runner=hook_runner,
        mcp_manager=mcp_manager,
    )
