"""Command base class — all slash commands inherit from this ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Command(ABC):
    """Base class for /slash commands. Subclasses implement name/description/execute."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Command name without the / prefix."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description shown in /help."""

    @abstractmethod
    async def execute(self, args: str, context: CommandContext) -> str | None:
        """Execute the command. Return optional output string, or None for no output."""


class CommandContext:
    """Shared context passed to commands — holds references to agent and other state."""

    def __init__(self, agent: object) -> None:
        self.agent = agent
        self.should_exit: bool = False
