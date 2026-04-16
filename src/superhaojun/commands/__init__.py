"""Commands package — Command ABC, CommandRegistry, and built-in commands."""

from .base import Command, CommandContext
from .builtins import (
    ClearCommand, CompactCommand, ExitCommand, HelpCommand,
    ExtensionsCommand,
    MemoryCommand, MessagesCommand, ModelCommand, QuitCommand,
    SessionCommand, ToolsCommand,
)
from .registry import CommandRegistry

__all__ = [
    "Command",
    "CommandContext",
    "CommandRegistry",
    "register_builtin_commands",
]


def register_builtin_commands(registry: CommandRegistry) -> None:
    """Register all built-in slash commands."""
    from ..mcp.commands import MCPCommand

    for cmd_cls in (HelpCommand, ClearCommand, CompactCommand, QuitCommand, ExitCommand,
                    MemoryCommand, MessagesCommand, ModelCommand, SessionCommand,
                    ExtensionsCommand,
                    ToolsCommand, MCPCommand):
        registry.register(cmd_cls())
