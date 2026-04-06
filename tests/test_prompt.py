"""Tests for Feature 7: System Prompt Engineering — SystemPromptBuilder."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from superhaojun.prompt.builder import SystemPromptBuilder


class TestSystemPromptBuilderBasic:
    """Base assembly without project context."""

    def test_default_sections(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp")
        prompt = builder.build()
        assert "SuperHaojun" in prompt
        assert len(prompt) > 50

    def test_includes_tool_descriptions(self) -> None:
        tools = [
            {"name": "read_file", "description": "Read a file from disk"},
            {"name": "bash", "description": "Run shell commands"},
        ]
        builder = SystemPromptBuilder(working_dir="/tmp", tool_summaries=tools)
        prompt = builder.build()
        assert "read_file" in prompt
        assert "bash" in prompt

    def test_includes_working_directory(self) -> None:
        builder = SystemPromptBuilder(working_dir="/home/user/project")
        prompt = builder.build()
        assert "/home/user/project" in prompt

    def test_includes_custom_instructions(self) -> None:
        builder = SystemPromptBuilder(
            working_dir="/tmp",
            custom_instructions="Always use type hints.",
        )
        prompt = builder.build()
        assert "Always use type hints." in prompt

    def test_empty_custom_instructions_not_in_prompt(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp", custom_instructions="")
        prompt = builder.build()
        assert "Custom Instructions" not in prompt

    def test_no_tools_section_when_empty(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp", tool_summaries=[])
        prompt = builder.build()
        assert "Available Tools" not in prompt


class TestProjectInstructionFiles:
    """Discovery of AGENT.md / CLAUDE.md / SUPERHAOJUN.md."""

    def test_loads_agent_md(self, tmp_path: Path) -> None:
        (tmp_path / "AGENT.md").write_text("Be concise and clear.")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "Be concise and clear." in prompt

    def test_loads_claude_md(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("Follow PEP8.")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "Follow PEP8." in prompt

    def test_loads_superhaojun_md(self, tmp_path: Path) -> None:
        (tmp_path / "SUPERHAOJUN.md").write_text("Use dataclasses.")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "Use dataclasses." in prompt

    def test_multiple_files_all_included(self, tmp_path: Path) -> None:
        (tmp_path / "AGENT.md").write_text("Agent rule.")
        (tmp_path / "CLAUDE.md").write_text("Claude rule.")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "Agent rule." in prompt
        assert "Claude rule." in prompt

    def test_missing_files_no_error(self, tmp_path: Path) -> None:
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "Project Instructions" not in prompt

    def test_nested_claude_md_in_dot_dir(self, tmp_path: Path) -> None:
        """Discovery in .claude/ subdirectory."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "CLAUDE.md").write_text("Nested rule.")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "Nested rule." in prompt


class TestGitContext:
    """Git status / branch injection."""

    def test_git_info_included_when_available(self, tmp_path: Path) -> None:
        """If working_dir is a git repo, branch info should appear."""
        # Initialize a real git repo with an initial commit
        os.system(
            f"cd {tmp_path} && git init -q -b main "
            f"&& git config user.email test@test.com && git config user.name test "
            f"&& touch .gitkeep && git add . && git commit -q -m init"
        )
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "main" in prompt

    def test_no_git_graceful(self, tmp_path: Path) -> None:
        """Non-git directory produces no git section."""
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "Git" not in prompt or "no git" in prompt.lower()


class TestSectionOrdering:
    """Sections appear in consistent order."""

    def test_base_before_project(self, tmp_path: Path) -> None:
        (tmp_path / "AGENT.md").write_text("Project specific.")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        base_idx = prompt.index("SuperHaojun")
        project_idx = prompt.index("Project specific.")
        assert base_idx < project_idx

    def test_custom_instructions_at_end(self, tmp_path: Path) -> None:
        (tmp_path / "AGENT.md").write_text("Project rule.")
        builder = SystemPromptBuilder(
            working_dir=str(tmp_path),
            custom_instructions="Custom rule here.",
        )
        prompt = builder.build()
        project_idx = prompt.index("Project rule.")
        custom_idx = prompt.index("Custom rule here.")
        assert custom_idx > project_idx


class TestCaching:
    """Builder caches result, invalidates on rebuild()."""

    def test_build_is_cached(self, tmp_path: Path) -> None:
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        first = builder.build()
        second = builder.build()
        assert first is second  # same object reference

    def test_rebuild_refreshes(self, tmp_path: Path) -> None:
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        first = builder.build()
        builder.invalidate()
        second = builder.build()
        assert first == second  # same content, different object
        assert first is not second
