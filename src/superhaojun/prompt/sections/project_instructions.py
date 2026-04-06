"""ProjectInstructionsSection — recursive discovery of instruction files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import PromptSection
from ...constants import BRAND_DIR, INSTRUCTION_FILES

if TYPE_CHECKING:
    from ..context import PromptContext


class ProjectInstructionsSection(PromptSection):
    @property
    def name(self) -> str:
        return "project_instructions"

    @property
    def cacheable(self) -> bool:
        return True

    def build(self, ctx: PromptContext) -> str | None:
        if not ctx.working_dir:
            return None
        contents = _discover_instructions(ctx.working_dir)
        if not contents:
            return None
        return "## Project Instructions\n\n" + "\n\n".join(contents)


def _discover_instructions(working_dir: str) -> list[str]:
    """Recursively discover instruction files from cwd up to filesystem root.

    Strategy (matching Claude Code):
    - Walk from working_dir upward to root
    - At each level, check for INSTRUCTION_FILES in the directory itself
      and in the .haojun/ subdirectory
    - Ancestor instructions appear first (lower priority), cwd instructions last (higher priority)
    - Deduplicate by resolved file path
    """
    contents: list[str] = []
    seen_paths: set[Path] = set()
    ancestors: list[Path] = []

    current = Path(working_dir).resolve()
    while True:
        ancestors.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Reverse: root first → cwd last (ancestor instructions before local)
    for dir_path in reversed(ancestors):
        search_dirs = [dir_path]
        brand_dir = dir_path / BRAND_DIR
        if brand_dir.is_dir():
            search_dirs.append(brand_dir)

        for search_dir in search_dirs:
            for filename in INSTRUCTION_FILES:
                filepath = (search_dir / filename).resolve()
                if filepath in seen_paths:
                    continue
                if filepath.is_file():
                    seen_paths.add(filepath)
                    text = filepath.read_text(encoding="utf-8").strip()
                    if text:
                        rel = filepath.relative_to(Path(working_dir).resolve()) if filepath.is_relative_to(Path(working_dir).resolve()) else filepath
                        contents.append(f"### {rel}\n{text}")

    return contents
