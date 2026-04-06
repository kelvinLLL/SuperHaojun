"""EnvironmentSection — working directory, git info, platform info."""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING

from . import PromptSection

if TYPE_CHECKING:
    from ..context import PromptContext


class EnvironmentSection(PromptSection):
    @property
    def name(self) -> str:
        return "environment"

    @property
    def cacheable(self) -> bool:
        return False

    def build(self, ctx: PromptContext) -> str | None:
        parts = [f"## Environment\n- Working directory: `{ctx.working_dir}`"]
        parts.append(f"- Platform: {platform.system()} {platform.machine()}")

        git = ctx.git_info
        if git and git.available:
            parts.append(f"- Git branch: `{git.branch}`")
            if git.status:
                parts.append(f"- Git status:\n```\n{git.status}\n```")
            if git.log:
                parts.append(f"- Recent commits:\n```\n{git.log}\n```")
            if git.diff_stat:
                parts.append(f"- Uncommitted changes:\n```\n{git.diff_stat}\n```")

        return "\n".join(parts)
