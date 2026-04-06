"""SessionContextSection — current session summary from compaction history."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import PromptSection

if TYPE_CHECKING:
    from ..context import PromptContext


class SessionContextSection(PromptSection):
    @property
    def name(self) -> str:
        return "session_context"

    @property
    def cacheable(self) -> bool:
        return False

    def build(self, ctx: PromptContext) -> str | None:
        if not ctx.session_summary:
            return None
        return f"## Session Context\n{ctx.session_summary}"
