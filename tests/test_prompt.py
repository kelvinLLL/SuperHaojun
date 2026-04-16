"""Tests for Feature 7 v2: System Prompt Engineering — Section Registry."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from superhaojun.constants import BRAND_DIR, INSTRUCTION_FILES, SYSTEM_PROMPT_DYNAMIC_BOUNDARY
from superhaojun.prompt.builder import SystemPromptBuilder
from superhaojun.prompt.context import GitInfo, PromptContext, gather_git_info
from superhaojun.prompt.sections import PromptSection
from superhaojun.prompt.sections.custom import CustomInstructionsSection
from superhaojun.prompt.sections.environment import EnvironmentSection
from superhaojun.prompt.sections.identity import IdentitySection
from superhaojun.prompt.sections.memory import MemorySection
from superhaojun.prompt.sections.project_instructions import ProjectInstructionsSection
from superhaojun.prompt.sections.session_context import SessionContextSection
from superhaojun.prompt.sections.tools import ToolsSection


# ── PromptContext + GitInfo ──


class TestGitInfo:
    def test_empty_git_info_not_available(self) -> None:
        gi = GitInfo()
        assert not gi.available

    def test_git_info_with_branch_is_available(self) -> None:
        gi = GitInfo(branch="main")
        assert gi.available

    def test_frozen(self) -> None:
        gi = GitInfo(branch="main")
        with pytest.raises(AttributeError):
            gi.branch = "dev"  # type: ignore[misc]


class TestPromptContext:
    def test_defaults(self) -> None:
        ctx = PromptContext()
        assert ctx.working_dir == ""
        assert ctx.tool_summaries == []
        assert ctx.memory_text == ""
        assert ctx.memory_metadata is None
        assert ctx.git_info is None

    def test_custom_fields(self) -> None:
        ctx = PromptContext(
            working_dir="/tmp",
            tool_summaries=[{"name": "bash", "description": "Run commands"}],
            memory_text="some memory",
            memory_metadata={"entry_count": 1},
            custom_instructions="be nice",
            session_summary="did stuff",
        )
        assert ctx.working_dir == "/tmp"
        assert len(ctx.tool_summaries) == 1
        assert ctx.memory_metadata == {"entry_count": 1}
        assert ctx.session_summary == "did stuff"


# ── PromptSection ABC ──


class TestPromptSectionABC:
    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            PromptSection()  # type: ignore[abstract]

    def test_default_cacheable_is_true(self) -> None:
        class TestSection(PromptSection):
            @property
            def name(self) -> str:
                return "test"
            def build(self, ctx: PromptContext) -> str | None:
                return "test content"

        s = TestSection()
        assert s.cacheable is True


# ── Individual Sections ──


class TestIdentitySection:
    def test_content(self) -> None:
        section = IdentitySection()
        content = section.build(PromptContext())
        assert "SuperHaojun" in content
        assert "concise" in content.lower()

    def test_cacheable(self) -> None:
        assert IdentitySection().cacheable is True


class TestToolsSection:
    def test_with_tools(self) -> None:
        ctx = PromptContext(tool_summaries=[
            {"name": "read_file", "description": "Read a file"},
            {"name": "bash", "description": "Run commands"},
        ])
        content = ToolsSection().build(ctx)
        assert "read_file" in content
        assert "bash" in content

    def test_empty_tools_returns_none(self) -> None:
        assert ToolsSection().build(PromptContext()) is None

    def test_cacheable(self) -> None:
        assert ToolsSection().cacheable is True


class TestProjectInstructionsSection:
    def test_uses_loaded_extensions_when_present(self) -> None:
        ctx = PromptContext(extensions=[
            {
                "id": "instruction:SUPERHAOJUN.md",
                "kind": "instruction",
                "name": "SUPERHAOJUN.md",
                "source": "SUPERHAOJUN.md",
                "enabled": True,
                "prompt_enabled": True,
                "scope": "repo",
                "prompt_text": "Use dataclasses.",
            },
            {
                "id": "workflow_rules:specs/development-rules.md",
                "kind": "workflow_rules",
                "name": "development-rules.md",
                "source": "specs/development-rules.md",
                "enabled": True,
                "prompt_enabled": True,
                "scope": "repo",
                "prompt_text": "Explainability First.",
            },
        ])
        content = ProjectInstructionsSection().build(ctx)
        assert "Use dataclasses." in content
        assert "Explainability First." in content

    def test_discovers_superhaojun_md(self, tmp_path: Path) -> None:
        (tmp_path / "SUPERHAOJUN.md").write_text("Use dataclasses.")
        ctx = PromptContext(working_dir=str(tmp_path))
        content = ProjectInstructionsSection().build(ctx)
        assert "Use dataclasses." in content

    def test_discovers_agent_md(self, tmp_path: Path) -> None:
        (tmp_path / "AGENT.md").write_text("Be concise.")
        ctx = PromptContext(working_dir=str(tmp_path))
        content = ProjectInstructionsSection().build(ctx)
        assert "Be concise." in content

    def test_does_not_search_claude_md(self, tmp_path: Path) -> None:
        """v2 brand abstraction: no CLAUDE.md discovery."""
        (tmp_path / "CLAUDE.md").write_text("Claude specific.")
        ctx = PromptContext(working_dir=str(tmp_path))
        content = ProjectInstructionsSection().build(ctx)
        assert content is None

    def test_brand_dir_discovery(self, tmp_path: Path) -> None:
        """Discovers files in .haojun/ subdirectory."""
        brand = tmp_path / BRAND_DIR
        brand.mkdir()
        (brand / "SUPERHAOJUN.md").write_text("Brand dir rule.")
        ctx = PromptContext(working_dir=str(tmp_path))
        content = ProjectInstructionsSection().build(ctx)
        assert "Brand dir rule." in content

    def test_recursive_discovery(self, tmp_path: Path) -> None:
        """Discovers ancestor instruction files (root first, cwd last)."""
        child = tmp_path / "sub" / "project"
        child.mkdir(parents=True)
        (tmp_path / "SUPERHAOJUN.md").write_text("Root rule.")
        (child / "SUPERHAOJUN.md").write_text("Child rule.")
        ctx = PromptContext(working_dir=str(child))
        content = ProjectInstructionsSection().build(ctx)
        assert "Root rule." in content
        assert "Child rule." in content
        root_idx = content.index("Root rule.")
        child_idx = content.index("Child rule.")
        assert root_idx < child_idx

    def test_deduplicates_by_path(self, tmp_path: Path) -> None:
        (tmp_path / "SUPERHAOJUN.md").write_text("Only once.")
        ctx = PromptContext(working_dir=str(tmp_path))
        content = ProjectInstructionsSection().build(ctx)
        assert content.count("Only once.") == 1

    def test_empty_file_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "SUPERHAOJUN.md").write_text("   ")
        ctx = PromptContext(working_dir=str(tmp_path))
        content = ProjectInstructionsSection().build(ctx)
        assert content is None

    def test_missing_files_returns_none(self, tmp_path: Path) -> None:
        ctx = PromptContext(working_dir=str(tmp_path))
        assert ProjectInstructionsSection().build(ctx) is None


class TestCustomInstructionsSection:
    def test_with_content(self) -> None:
        ctx = PromptContext(custom_instructions="Always use type hints.")
        content = CustomInstructionsSection().build(ctx)
        assert "Always use type hints." in content

    def test_empty_returns_none(self) -> None:
        assert CustomInstructionsSection().build(PromptContext()) is None


class TestEnvironmentSection:
    def test_includes_working_dir(self) -> None:
        ctx = PromptContext(working_dir="/home/user/project")
        content = EnvironmentSection().build(ctx)
        assert "/home/user/project" in content

    def test_includes_git_info(self) -> None:
        ctx = PromptContext(
            working_dir="/tmp",
            git_info=GitInfo(branch="main", status="M file.py"),
        )
        content = EnvironmentSection().build(ctx)
        assert "main" in content
        assert "M file.py" in content

    def test_uncacheable(self) -> None:
        assert EnvironmentSection().cacheable is False

    def test_no_git_info(self) -> None:
        ctx = PromptContext(working_dir="/tmp")
        content = EnvironmentSection().build(ctx)
        assert "branch" not in content.lower()


class TestMemorySection:
    def test_with_memory(self) -> None:
        ctx = PromptContext(memory_text="[user]\n- Prefers Python.")
        content = MemorySection().build(ctx)
        assert "Prefers Python." in content
        assert "previous sessions" in content.lower()
        assert "verify" in content.lower()

    def test_empty_returns_none(self) -> None:
        assert MemorySection().build(PromptContext()) is None

    def test_uncacheable(self) -> None:
        assert MemorySection().cacheable is False


class TestSessionContextSection:
    def test_with_summary(self) -> None:
        ctx = PromptContext(session_summary="Refactored agent.py...")
        content = SessionContextSection().build(ctx)
        assert "Refactored agent.py..." in content

    def test_empty_returns_none(self) -> None:
        assert SessionContextSection().build(PromptContext()) is None

    def test_uncacheable(self) -> None:
        assert SessionContextSection().cacheable is False


# ── Git 5-way Parallel ──


class TestGatherGitInfo:
    def test_in_real_git_repo(self, tmp_path: Path) -> None:
        os.system(
            f"cd {tmp_path} && git init -q -b main "
            f"&& git config user.email test@test.com && git config user.name test "
            f"&& touch .gitkeep && git add . && git commit -q -m init"
        )
        info = asyncio.get_event_loop().run_until_complete(gather_git_info(str(tmp_path)))
        assert info.available
        assert info.branch == "main"

    def test_non_git_dir(self, tmp_path: Path) -> None:
        info = asyncio.get_event_loop().run_until_complete(gather_git_info(str(tmp_path)))
        assert not info.available


# ── SystemPromptBuilder v2 ──


class TestSystemPromptBuilderV2:
    def test_default_build(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp")
        prompt = builder.build()
        assert "SuperHaojun" in prompt
        assert len(prompt) > 100

    def test_dynamic_boundary_present(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp")
        prompt = builder.build()
        assert SYSTEM_PROMPT_DYNAMIC_BOUNDARY in prompt

    def test_cacheable_before_uncacheable(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp")
        prompt = builder.build()
        boundary_idx = prompt.index(SYSTEM_PROMPT_DYNAMIC_BOUNDARY)
        identity_idx = prompt.index("SuperHaojun")
        assert identity_idx < boundary_idx

    def test_includes_tools(self) -> None:
        tools = [{"name": "read_file", "description": "Read a file"}]
        builder = SystemPromptBuilder(working_dir="/tmp", tool_summaries=tools)
        prompt = builder.build()
        assert "read_file" in prompt

    def test_includes_custom_instructions(self) -> None:
        builder = SystemPromptBuilder(
            working_dir="/tmp", custom_instructions="Always use type hints."
        )
        prompt = builder.build()
        assert "Always use type hints." in prompt

    def test_includes_memory(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp", memory_text="User likes Python.")
        prompt = builder.build()
        assert "User likes Python." in prompt

    def test_caching(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp")
        first = builder.build()
        second = builder.build()
        assert first is second

    def test_invalidate(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp")
        first = builder.build()
        builder.invalidate()
        second = builder.build()
        assert first is not second
        assert first == second

    def test_set_memory_text_invalidates(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp")
        first = builder.build()
        builder.set_memory_text("New memory")
        second = builder.build()
        assert first is not second
        assert "New memory" in second

    def test_set_memory_entry_tracks_metadata(self) -> None:
        from superhaojun.memory.store import MemoryPromptEntry

        builder = SystemPromptBuilder(working_dir="/tmp")
        builder.set_memory_entry(MemoryPromptEntry(
            text="Memory Index\n\nLoaded Topics\n- test",
            loaded_entries=[{"id": "abc12345", "name": "Test", "category": "user", "source": "user_test.md", "chars": 4}],
            truncated=False,
            total_chars=30,
            index_chars=12,
            topic_chars=18,
        ))
        prompt = builder.build()

        assert "Loaded Topics" in prompt
        assert builder.memory_entry_metadata == {
            "loaded_entries": [{"id": "abc12345", "name": "Test", "category": "user", "source": "user_test.md", "chars": 4}],
            "truncated": False,
            "total_chars": 30,
            "index_chars": 12,
            "topic_chars": 18,
        }

    def test_set_session_summary(self) -> None:
        builder = SystemPromptBuilder(working_dir="/tmp")
        builder.set_session_summary("Did refactoring work")
        prompt = builder.build()
        assert "Did refactoring work" in prompt

    def test_register_custom_section(self) -> None:
        class ExtraSection(PromptSection):
            @property
            def name(self) -> str:
                return "extra"
            def build(self, ctx: PromptContext) -> str | None:
                return "Extra content here."

        builder = SystemPromptBuilder(working_dir="/tmp")
        builder.register_section(ExtraSection())
        prompt = builder.build()
        assert "Extra content here." in prompt

    def test_project_instructions_with_brand_dir(self, tmp_path: Path) -> None:
        brand = tmp_path / BRAND_DIR
        brand.mkdir()
        (brand / "SUPERHAOJUN.md").write_text("Brand instructions.")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "Brand instructions." in prompt

    def test_includes_development_rules_via_extensions_runtime(self, tmp_path: Path) -> None:
        specs = tmp_path / "specs"
        specs.mkdir()
        (specs / "development-rules.md").write_text("Explainability First.")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "Explainability First." in prompt

    def test_backward_compat_no_claude_md(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("Claude rule.")
        builder = SystemPromptBuilder(working_dir=str(tmp_path))
        prompt = builder.build()
        assert "Claude rule." not in prompt


class TestBrandConstants:
    def test_brand_name(self) -> None:
        from superhaojun.constants import BRAND_NAME
        assert BRAND_NAME == "haojun"

    def test_brand_dir(self) -> None:
        from superhaojun.constants import BRAND_DIR
        assert BRAND_DIR == ".haojun"

    def test_instruction_files_no_claude(self) -> None:
        assert "CLAUDE.md" not in INSTRUCTION_FILES
        assert "SUPERHAOJUN.md" in INSTRUCTION_FILES
        assert "AGENT.md" in INSTRUCTION_FILES
