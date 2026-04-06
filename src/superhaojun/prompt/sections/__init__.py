"""PromptSection ABC — base class for all system prompt sections."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import PromptContext


class PromptSection(ABC):
    """A single section of the system prompt.

    Sections are assembled by SystemPromptBuilder in registry order.
    Cacheable sections are placed before uncacheable ones, separated by
    SYSTEM_PROMPT_DYNAMIC_BOUNDARY.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Section identifier (used for logging / debugging)."""

    @property
    def cacheable(self) -> bool:
        """True = content is stable across turns, eligible for prompt cache.
        False = content may change every turn (git status, memory, etc.)."""
        return True

    @abstractmethod
    def build(self, ctx: PromptContext) -> str | None:
        """Build section content. Return None to skip this section."""
