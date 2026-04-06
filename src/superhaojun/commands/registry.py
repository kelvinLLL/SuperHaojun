"""CommandRegistry — manages registered slash commands."""

from __future__ import annotations

from .base import Command


class CommandRegistry:
    """Manages registered slash commands, provides lookup and completion."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        self._commands[command.name] = command

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)

    def completions(self, prefix: str = "") -> list[str]:
        """Return sorted command names matching the given prefix."""
        return sorted(
            name for name in self._commands
            if name.startswith(prefix)
        )

    def all(self) -> list[Command]:
        return list(self._commands.values())

    def __len__(self) -> int:
        return len(self._commands)
