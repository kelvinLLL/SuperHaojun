"""ToolsSection — available tool descriptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import PromptSection

if TYPE_CHECKING:
    from ..context import PromptContext


class ToolsSection(PromptSection):
    @property
    def name(self) -> str:
        return "tools"

    @property
    def cacheable(self) -> bool:
        return True

    def build(self, ctx: PromptContext) -> str | None:
        if not ctx.tool_summaries:
            return None
        lines = ["## Available Tools"]
        for ts in ctx.tool_summaries:
            lines.append(f"- **{ts['name']}**: {ts.get('description', '')}")
        return "\n".join(lines)
