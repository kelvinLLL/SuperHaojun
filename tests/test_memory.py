"""Tests for Feature 10 v2: Markdown-based Memory System + Auto-Extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from superhaojun.memory.store import (
    MemoryCategory,
    MemoryEntry,
    MemoryPromptEntry,
    MemoryStore,
    _entry_from_markdown,
    _entry_to_markdown,
    _safe_filename,
)
from superhaojun.memory.extractor import extract_memories


# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------
class TestMemoryEntry:
    def test_fields(self) -> None:
        entry = MemoryEntry(category=MemoryCategory.USER, content="dark mode")
        assert entry.category == MemoryCategory.USER
        assert entry.content == "dark mode"
        assert entry.entry_id
        assert entry.created_at > 0

    def test_unique_ids(self) -> None:
        e1 = MemoryEntry(category=MemoryCategory.PROJECT, content="a")
        e2 = MemoryEntry(category=MemoryCategory.PROJECT, content="b")
        assert e1.entry_id != e2.entry_id

    def test_auto_name_from_content(self) -> None:
        entry = MemoryEntry(category=MemoryCategory.USER, content="User prefers dark mode always")
        assert entry.name == "User prefers dark mode always"

    def test_explicit_name(self) -> None:
        entry = MemoryEntry(category=MemoryCategory.USER, content="abc", name="Theme Preference")
        assert entry.name == "Theme Preference"


# ---------------------------------------------------------------------------
# Markdown serialization
# ---------------------------------------------------------------------------
class TestMarkdownSerialization:
    def test_roundtrip(self) -> None:
        entry = MemoryEntry(
            category=MemoryCategory.FEEDBACK,
            content="Avoid global mutable state.",
            name="No Globals",
            description="Coding pattern",
            entry_id="abc123",
            created_at=1000.0,
        )
        md = _entry_to_markdown(entry)
        assert "---" in md
        assert "type: feedback" in md
        assert "id: abc123" in md
        parsed = _entry_from_markdown(md)
        assert parsed is not None
        assert parsed.entry_id == "abc123"
        assert parsed.category == MemoryCategory.FEEDBACK
        assert parsed.content == "Avoid global mutable state."
        assert parsed.name == "No Globals"

    def test_invalid_markdown_returns_none(self) -> None:
        assert _entry_from_markdown("just plain text") is None

    def test_unknown_category_defaults_to_user(self) -> None:
        md = "---\nname: x\ndescription: y\ntype: alien\nid: z\ncreated_at: 0\n---\ncontent"
        entry = _entry_from_markdown(md)
        assert entry is not None
        assert entry.category == MemoryCategory.USER

    def test_safe_filename(self) -> None:
        entry = MemoryEntry(category=MemoryCategory.USER, content="Hello World!", entry_id="abcdef12")
        name = _safe_filename(entry)
        assert name.startswith("user_")
        assert name.endswith(".md")
        assert "abcdef12" in name

    def test_safe_filename_empty_name(self) -> None:
        entry = MemoryEntry(category=MemoryCategory.USER, content="", name="", entry_id="xyz78901")
        name = _safe_filename(entry)
        assert "xyz78901" in name


# ---------------------------------------------------------------------------
# MemoryStore — CRUD
# ---------------------------------------------------------------------------
class TestMemoryStoreCRUD:
    def test_add_and_get(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        entry = store.add(MemoryCategory.USER, "Prefers Python.")
        assert entry.content == "Prefers Python."
        retrieved = store.get(entry.entry_id)
        assert retrieved is not None
        assert retrieved.content == "Prefers Python."

    def test_list_by_category(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "user pref")
        store.add(MemoryCategory.PROJECT, "project note")
        store.add(MemoryCategory.USER, "another user pref")
        assert len(store.list_entries(MemoryCategory.USER)) == 2
        assert len(store.list_entries(MemoryCategory.PROJECT)) == 1

    def test_list_all(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "u1")
        store.add(MemoryCategory.FEEDBACK, "f1")
        assert len(store.list_entries()) == 2

    def test_delete(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        entry = store.add(MemoryCategory.USER, "to delete")
        assert store.delete(entry.entry_id) is True
        assert store.get(entry.entry_id) is None

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        assert store.delete("nonexistent") is False

    def test_clear(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "a")
        store.add(MemoryCategory.PROJECT, "b")
        store.clear()
        assert store.list_entries() == []
        # Files cleaned
        assert list(tmp_path.glob("*.md")) == []

    def test_search(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "Python type hints are preferred")
        store.add(MemoryCategory.USER, "Use dataclasses over dict")
        results = store.search("type")
        assert len(results) == 1
        assert "type hints" in results[0].content


# ---------------------------------------------------------------------------
# MemoryStore — Persistence
# ---------------------------------------------------------------------------
class TestMemoryStorePersistence:
    def test_add_auto_persists(self, tmp_path: Path) -> None:
        """add() writes .md file immediately."""
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "auto-saved")
        md_files = list(tmp_path.glob("user_*.md"))
        assert len(md_files) == 1

    def test_reload_from_disk(self, tmp_path: Path) -> None:
        store1 = MemoryStore(storage_dir=tmp_path)
        store1.add(MemoryCategory.USER, "persisted")
        # New store reads from disk
        store2 = MemoryStore(storage_dir=tmp_path)
        entries = store2.list_entries()
        assert len(entries) == 1
        assert entries[0].content == "persisted"

    def test_index_file_generated(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "item one")
        index = tmp_path / "MEMORY.md"
        assert index.exists()
        text = index.read_text()
        assert "Memory Index" in text
        assert "item one" in text

    def test_index_removed_when_empty(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        entry = store.add(MemoryCategory.USER, "temp")
        store.delete(entry.entry_id)
        assert not (tmp_path / "MEMORY.md").exists()

    def test_delete_removes_file(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        entry = store.add(MemoryCategory.USER, "delete me")
        md_before = list(tmp_path.glob("user_*.md"))
        assert len(md_before) == 1
        store.delete(entry.entry_id)
        md_after = list(tmp_path.glob("user_*.md"))
        assert len(md_after) == 0


# ---------------------------------------------------------------------------
# MemoryStore — Legacy migration
# ---------------------------------------------------------------------------
class TestLegacyMigration:
    def test_migrate_from_json(self, tmp_path: Path) -> None:
        """Auto-migrate legacy memory.json to markdown files."""
        legacy = [
            {"entry_id": "abc1", "category": "user", "content": "old note", "created_at": 100.0},
            {"entry_id": "abc2", "category": "project", "content": "proj info", "created_at": 200.0},
        ]
        (tmp_path / "memory.json").write_text(json.dumps(legacy), encoding="utf-8")
        store = MemoryStore(storage_dir=tmp_path)
        entries = store.list_entries()
        assert len(entries) == 2
        # Legacy file removed
        assert not (tmp_path / "memory.json").exists()
        # .md files created
        md_files = [f for f in tmp_path.glob("*.md") if f.name != "MEMORY.md"]
        assert len(md_files) == 2

    def test_migrate_empty_json(self, tmp_path: Path) -> None:
        (tmp_path / "memory.json").write_text("[]", encoding="utf-8")
        store = MemoryStore(storage_dir=tmp_path)
        assert store.list_entries() == []
        assert not (tmp_path / "memory.json").exists()

    def test_migrate_corrupted_json(self, tmp_path: Path) -> None:
        (tmp_path / "memory.json").write_text("NOT JSON", encoding="utf-8")
        store = MemoryStore(storage_dir=tmp_path)
        assert store.list_entries() == []


# ---------------------------------------------------------------------------
# MemoryStore — Prompt text
# ---------------------------------------------------------------------------
class TestPromptText:
    def test_build_prompt_entry_uses_index_and_bounded_topic_expansion(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        first = store.add(
            MemoryCategory.USER,
            "User prefers concise responses and clear summaries.",
            name="Response Style",
            description="User preference",
        )
        second = store.add(
            MemoryCategory.PROJECT,
            "Project uses uv for environment management and pytest for tests.",
            name="Tooling",
            description="Project setup",
        )
        entry = store.build_prompt_entry(
            index_char_limit=120,
            max_topics=1,
            topic_char_limit=40,
            total_topic_char_limit=40,
        )

        assert isinstance(entry, MemoryPromptEntry)
        assert "Memory Index" in entry.text
        assert "Loaded Topics" in entry.text
        assert len(entry.loaded_entries) == 1
        assert entry.loaded_entries[0]["id"] == second.entry_id[:8]
        assert entry.loaded_entries[0]["name"] == "Tooling"
        assert entry.loaded_entries[0]["category"] == MemoryCategory.PROJECT.value
        assert entry.truncated is True
        assert first.entry_id[:8] not in entry.text

    def test_to_prompt_text(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "Likes clean code.")
        store.add(MemoryCategory.PROJECT, "Uses uv package manager.")
        text = store.to_prompt_text()
        assert "Memory Index" in text
        assert "Loaded Topics" in text
        assert "uv package manager" in text

    def test_empty_prompt_text(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        assert store.to_prompt_text() == ""

    def test_grouped_by_category(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "u1")
        store.add(MemoryCategory.FEEDBACK, "f1")
        text = store.to_prompt_text()
        assert "## User" in text
        assert "## Feedback" in text


# ---------------------------------------------------------------------------
# MemoryStore — Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_large_content(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        big = "x" * 10000
        entry = store.add(MemoryCategory.USER, big)
        assert len(store.get(entry.entry_id).content) == 10000

    def test_special_chars_in_content(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        entry = store.add(MemoryCategory.USER, 'Use "quotes" and <brackets>')
        # Reload
        store2 = MemoryStore(storage_dir=tmp_path)
        loaded = store2.get(entry.entry_id)
        assert loaded is not None
        assert loaded.content == 'Use "quotes" and <brackets>'

    def test_multiline_content(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        content = "line1\nline2\nline3"
        entry = store.add(MemoryCategory.USER, content)
        store2 = MemoryStore(storage_dir=tmp_path)
        loaded = store2.get(entry.entry_id)
        assert loaded is not None
        assert loaded.content == content

    def test_add_with_name_and_description(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        entry = store.add(MemoryCategory.REFERENCE, "pydantic v2 uses model_validate", name="Pydantic API", description="Migration note")
        assert entry.name == "Pydantic API"
        assert entry.description == "Migration note"

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        store = MemoryStore(storage_dir=deep)
        entry = store.add(MemoryCategory.USER, "deep")
        assert deep.exists()
        assert store.get(entry.entry_id).content == "deep"


# ---------------------------------------------------------------------------
# Memory Extractor
# ---------------------------------------------------------------------------
class TestExtractor:
    @pytest.mark.asyncio
    async def test_extract_memories(self) -> None:
        response = json.dumps([
            {"category": "user", "content": "Prefers dark mode.", "name": "Theme"},
            {"category": "project", "content": "Uses uv.", "name": "Package Manager"},
        ])
        async def fake_llm(sys: str, user: str) -> str:
            return response

        entries = await extract_memories("session about theme and tooling", fake_llm)
        assert len(entries) == 2
        assert entries[0].category == MemoryCategory.USER
        assert entries[0].content == "Prefers dark mode."
        assert entries[1].category == MemoryCategory.PROJECT

    @pytest.mark.asyncio
    async def test_extract_empty_summary(self) -> None:
        async def fake_llm(sys: str, user: str) -> str:
            return "[]"
        entries = await extract_memories("", fake_llm)
        assert entries == []

    @pytest.mark.asyncio
    async def test_extract_invalid_json(self) -> None:
        async def fake_llm(sys: str, user: str) -> str:
            return "not json at all"
        entries = await extract_memories("some summary", fake_llm)
        assert entries == []

    @pytest.mark.asyncio
    async def test_extract_with_markdown_fences(self) -> None:
        inner = json.dumps([{"category": "feedback", "content": "Use type hints.", "name": "Types"}])
        response = f"```json\n{inner}\n```"
        async def fake_llm(sys: str, user: str) -> str:
            return response
        entries = await extract_memories("session", fake_llm)
        assert len(entries) == 1
        assert entries[0].category == MemoryCategory.FEEDBACK

    @pytest.mark.asyncio
    async def test_extract_max_5_items(self) -> None:
        items = [{"category": "user", "content": f"item{i}", "name": f"n{i}"} for i in range(10)]
        async def fake_llm(sys: str, user: str) -> str:
            return json.dumps(items)
        entries = await extract_memories("big session", fake_llm)
        assert len(entries) == 5

    @pytest.mark.asyncio
    async def test_extract_unknown_category(self) -> None:
        response = json.dumps([{"category": "alien", "content": "xyz", "name": "test"}])
        async def fake_llm(sys: str, user: str) -> str:
            return response
        entries = await extract_memories("session", fake_llm)
        assert len(entries) == 1
        assert entries[0].category == MemoryCategory.USER

    @pytest.mark.asyncio
    async def test_extract_skips_empty_content(self) -> None:
        response = json.dumps([
            {"category": "user", "content": "", "name": "empty"},
            {"category": "user", "content": "real content", "name": "real"},
        ])
        async def fake_llm(sys: str, user: str) -> str:
            return response
        entries = await extract_memories("session", fake_llm)
        assert len(entries) == 1
        assert entries[0].content == "real content"


# ---------------------------------------------------------------------------
# All categories
# ---------------------------------------------------------------------------
class TestCategories:
    def test_all_categories(self) -> None:
        cats = list(MemoryCategory)
        assert MemoryCategory.USER in cats
        assert MemoryCategory.FEEDBACK in cats
        assert MemoryCategory.PROJECT in cats
        assert MemoryCategory.REFERENCE in cats
