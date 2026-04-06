"""SystemPromptBuilder — dynamic system prompt assembly.

Assembles sections in order:
1. Base instructions (identity, behavior)
2. Environment context (working dir, git info)
3. Project instructions (AGENT.md / CLAUDE.md / SUPERHAOJUN.md discovery)
4. Tool descriptions
5. Custom user instructions

Caches the built prompt; call invalidate() to force rebuild (e.g. on /clear, /compact).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


# Files to discover in working directory (and .claude/ subdir)
_INSTRUCTION_FILES = ("AGENT.md", "CLAUDE.md", "SUPERHAOJUN.md")

_BASE_PROMPT = (
    "You are SuperHaojun, a highly capable AI coding assistant.\n"
    "You help with programming tasks, code review, architecture design, and debugging.\n"
    "Be concise and direct. Respond in the same language the user uses.\n"
    "When writing code, follow clean code principles: clear naming, minimal comments, "
    "idiomatic patterns for the language in use."
)


class SystemPromptBuilder:
    """Dynamically assembles system prompt from multiple sections."""

    def __init__(
        self,
        working_dir: str,
        tool_summaries: list[dict[str, str]] | None = None,
        custom_instructions: str = "",
        memory_text: str = "",
    ) -> None:
        self._working_dir = working_dir
        self._tool_summaries = tool_summaries or []
        self._custom_instructions = custom_instructions
        self._memory_text = memory_text
        self._cached: str | None = None

    def build(self) -> str:
        if self._cached is not None:
            return self._cached
        sections: list[str] = []
        sections.append(self._base_section())
        sections.append(self._environment_section())
        project = self._project_instructions_section()
        if project:
            sections.append(project)
        tools = self._tools_section()
        if tools:
            sections.append(tools)
        memory = self._memory_section()
        if memory:
            sections.append(memory)
        custom = self._custom_section()
        if custom:
            sections.append(custom)
        self._cached = "\n\n".join(sections)
        return self._cached

    def invalidate(self) -> None:
        self._cached = None

    # ── Private section builders ──

    def _base_section(self) -> str:
        return _BASE_PROMPT

    def _environment_section(self) -> str:
        parts = [f"Working directory: {self._working_dir}"]
        git_info = self._gather_git_info()
        if git_info:
            parts.append(git_info)
        return "\n".join(parts)

    def _project_instructions_section(self) -> str | None:
        contents: list[str] = []
        root = Path(self._working_dir)

        search_dirs = [root]
        claude_dir = root / ".claude"
        if claude_dir.is_dir():
            search_dirs.append(claude_dir)

        for dir_path in search_dirs:
            for filename in _INSTRUCTION_FILES:
                filepath = dir_path / filename
                if filepath.is_file():
                    text = filepath.read_text(encoding="utf-8").strip()
                    if text:
                        contents.append(f"# {filename}\n{text}")

        if not contents:
            return None
        return "Project Instructions:\n\n" + "\n\n".join(contents)

    def _tools_section(self) -> str | None:
        if not self._tool_summaries:
            return None
        lines = ["Available Tools:"]
        for ts in self._tool_summaries:
            lines.append(f"- {ts['name']}: {ts.get('description', '')}")
        return "\n".join(lines)

    def _custom_section(self) -> str | None:
        if not self._custom_instructions:
            return None
        return f"Custom Instructions:\n{self._custom_instructions}"

    def _memory_section(self) -> str | None:
        if not self._memory_text:
            return None
        return f"Memory:\n{self._memory_text}"

    def _gather_git_info(self) -> str | None:
        try:
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, cwd=self._working_dir, timeout=5,
            )
            if branch.returncode != 0:
                return None

            branch_name = branch.stdout.strip()

            status = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True, text=True, cwd=self._working_dir, timeout=5,
            )
            status_text = status.stdout.strip()

            parts = [f"Git branch: {branch_name}"]
            if status_text:
                # Truncate to 200 chars like Claude Code
                if len(status_text) > 200:
                    status_text = status_text[:200] + "..."
                parts.append(f"Git status:\n{status_text}")
            return "\n".join(parts)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None
