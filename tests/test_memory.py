"""Tests for Feature 10: Memory System."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from superhaojun.memory.store import MemoryCategory, MemoryEntry, MemoryStore


class TestMemoryEntry:
    def test_fields(self) -> None:
        entry = MemoryEntry(
            category=MemoryCategory.USER,
            content="User prefers dark mode.",
        )
        assert entry.category == MemoryCategory.USER
        assert entry.content == "User prefers dark mode."
        assert entry.entry_id
        assert entry.created_at > 0

    def test_unique_ids(self) -> None:
        e1 = MemoryEntry(category=MemoryCategory.PROJECT, content="a")
        e2 = MemoryEntry(category=MemoryCategory.PROJECT, content="b")
        assert e1.entry_id != e2.entry_id


class TestMemoryStore:
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
        user_entries = store.list_entries(MemoryCategory.USER)
        assert len(user_entries) == 2

    def test_list_all(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "u1")
        store.add(MemoryCategory.FEEDBACK, "f1")
        all_entries = store.list_entries()
        assert len(all_entries) == 2

    def test_delete(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        entry = store.add(MemoryCategory.USER, "to delete")
        assert store.delete(entry.entry_id) is True
        assert store.get(entry.entry_id) is None

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        assert store.delete("nonexistent") is False

    def test_persistence(self, tmp_path: Path) -> None:
        store1 = MemoryStore(storage_dir=tmp_path)
        store1.add(MemoryCategory.USER, "persisted")
        store1.save()

        store2 = MemoryStore(storage_dir=tmp_path)
        store2.load()
        entries = store2.list_entries()
        assert len(entries) == 1
        assert entries[0].content == "persisted"

    def test_auto_save_on_add(self, tmp_path: Path) -> None:
        """add() auto-saves to disk."""
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "auto-saved")

        store2 = MemoryStore(storage_dir=tmp_path)
        store2.load()
        assert len(store2.list_entries()) == 1

    def test_clear(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "a")
        store.add(MemoryCategory.PROJECT, "b")
        store.clear()
        assert store.list_entries() == []

    def test_search(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "Python type hints are preferred")
        store.add(MemoryCategory.USER, "Use dataclasses over dict")
        store.add(MemoryCategory.FEEDBACK, "Good explanation of generics")
        results = store.search("type")
        assert len(results) == 1
        assert "type hints" in results[0].content

    def test_to_prompt_text(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        store.add(MemoryCategory.USER, "Likes clean code.")
        store.add(MemoryCategory.PROJECT, "Uses uv package manager.")
        text = store.to_prompt_text()
        assert "clean code" in text
        assert "uv package manager" in text
        assert "user" in text.lower() or "project" in text.lower()

    def test_empty_prompt_text(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        assert store.to_prompt_text() == ""


class TestMemoryCategories:
    def test_all_categories(self) -> None:
        cats = list(MemoryCategory)
        assert MemoryCategory.USER in cats
        assert MemoryCategory.FEEDBACK in cats
        assert MemoryCategory.PROJECT in cats
        assert MemoryCategory.REFERENCE in cats


class TestMemoryEdgeCases:
    def test_large_content(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        big = "x" * 10000
        entry = store.add(MemoryCategory.USER, big)
        assert len(store.get(entry.entry_id).content) == 10000

    def test_special_chars_in_content(self, tmp_path: Path) -> None:
        store = MemoryStore(storage_dir=tmp_path)
        entry = store.add(MemoryCategory.USER, 'Use "quotes" and <brackets>')
        loaded = store.get(entry.entry_id)
        assert loaded.content == 'Use "quotes" and <brackets>'
