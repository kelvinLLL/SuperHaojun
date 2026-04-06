"""SystemPromptBuilder v2 — Section Registry architecture.

Assembles prompt from registered PromptSection instances:
- Cacheable sections (identity, tools, project instructions, custom) come first
- SYSTEM_PROMPT_DYNAMIC_BOUNDARY separates cacheable from uncacheable
- Uncacheable sections (environment, memory, session context) come last

Caches the cacheable portion separately for prompt cache optimization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..constants import SYSTEM_PROMPT_DYNAMIC_BOUNDARY
from .context import GitInfo, PromptContext, gather_git_info_sync
from .sections import PromptSection
from .sections.custom import CustomInstructionsSection
from .sections.environment import EnvironmentSection
from .sections.identity import IdentitySection
from .sections.memory import MemorySection
from .sections.project_instructions import ProjectInstructionsSection
from .sections.session_context import SessionContextSection
from .sections.tools import ToolsSection


def _default_sections() -> list[PromptSection]:
    """Default section registry — cacheable first, uncacheable last."""
    return [
        # Cacheable (stable across turns)
        IdentitySection(),
        ToolsSection(),
        ProjectInstructionsSection(),
        CustomInstructionsSection(),
        # Uncacheable (may change every turn)
        EnvironmentSection(),
        MemorySection(),
        SessionContextSection(),
    ]


class SystemPromptBuilder:
    """Dynamically assembles system prompt from registered sections.

    Compatible with v1 API: __init__ accepts the same kwargs,
    build() returns a single string.
    """

    def __init__(
        self,
        working_dir: str,
        tool_summaries: list[dict[str, str]] | None = None,
        custom_instructions: str = "",
        memory_text: str = "",
        sections: list[PromptSection] | None = None,
    ) -> None:
        self._working_dir = working_dir
        self._tool_summaries = tool_summaries or []
        self._custom_instructions = custom_instructions
        self._memory_text = memory_text
        self._sections = sections if sections is not None else _default_sections()
        self._cached_static: str | None = None
        self._cached_full: str | None = None
        self._session_summary: str = ""

    @property
    def context(self) -> PromptContext:
        """Build the current PromptContext (used by sections)."""
        git_info = gather_git_info_sync(self._working_dir)
        return PromptContext(
            working_dir=self._working_dir,
            tool_summaries=self._tool_summaries,
            memory_text=self._memory_text,
            custom_instructions=self._custom_instructions,
            git_info=git_info,
            session_summary=self._session_summary,
        )

    def set_memory_text(self, text: str) -> None:
        self._memory_text = text
        self._cached_full = None  # dynamic part changed

    def set_session_summary(self, summary: str) -> None:
        self._session_summary = summary
        self._cached_full = None

    def build(self) -> str:
        """Build the complete system prompt."""
        if self._cached_full is not None:
            return self._cached_full

        ctx = self.context

        cacheable_parts: list[str] = []
        uncacheable_parts: list[str] = []

        for section in self._sections:
            content = section.build(ctx)
            if content is None:
                continue
            if section.cacheable:
                cacheable_parts.append(content)
            else:
                uncacheable_parts.append(content)

        parts = cacheable_parts[:]
        if uncacheable_parts:
            parts.append(SYSTEM_PROMPT_DYNAMIC_BOUNDARY)
            parts.extend(uncacheable_parts)

        self._cached_full = "\n\n".join(parts)
        return self._cached_full

    def invalidate(self) -> None:
        """Force rebuild on next build() call."""
        self._cached_static = None
        self._cached_full = None

    def register_section(self, section: PromptSection) -> None:
        """Add a section to the registry."""
        self._sections.append(section)
        self.invalidate()
