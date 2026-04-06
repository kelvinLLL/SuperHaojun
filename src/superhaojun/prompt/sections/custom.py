"""CustomInstructionsSection — user-provided custom instructions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import PromptSection

if TYPE_CHECKING:
    from ..context import PromptContext


class CustomInstructionsSection(PromptSection):
    @property
    def name(self) -> str:
        return "custom_instructions"

    @property
    def cacheable(self) -> bool:
        return True

    def build(self, ctx: PromptContext) -> str | None:
        if not ctx.custom_instructions:
            return None
        return f"## Custom Instructions\n{ctx.custom_instructions}"
