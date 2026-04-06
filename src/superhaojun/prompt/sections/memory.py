"""MemorySection — cross-session memory injection with guidance text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import PromptSection

if TYPE_CHECKING:
    from ..context import PromptContext


_MEMORY_GUIDANCE = """\
The following memories were persisted from previous sessions.
Use them as context but verify against current code state before acting.
Memory may be stale — if it conflicts with what you observe, trust current state."""


class MemorySection(PromptSection):
    @property
    def name(self) -> str:
        return "memory"

    @property
    def cacheable(self) -> bool:
        return False

    def build(self, ctx: PromptContext) -> str | None:
        if not ctx.memory_text:
            return None
        return f"## Memory\n{_MEMORY_GUIDANCE}\n\n{ctx.memory_text}"
