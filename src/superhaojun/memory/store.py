"""MemoryStore — cross-session persistent memory (MEMORY.md pattern).

Categories: user, feedback, project, reference.
Storage: single JSON file in configurable directory.
Injection: to_prompt_text() produces text for system prompt inclusion.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


class MemoryCategory(StrEnum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


@dataclass
class MemoryEntry:
    category: MemoryCategory
    content: str
    entry_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: float = field(default_factory=time.time)


def _entry_to_dict(entry: MemoryEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "category": entry.category.value,
        "content": entry.content,
        "created_at": entry.created_at,
    }


def _entry_from_dict(data: dict[str, Any]) -> MemoryEntry:
    return MemoryEntry(
        entry_id=data["entry_id"],
        category=MemoryCategory(data["category"]),
        content=data["content"],
        created_at=data.get("created_at", 0),
    )


class MemoryStore:
    """Persistent memory store backed by a JSON file."""

    def __init__(self, storage_dir: Path | str) -> None:
        self._storage_dir = Path(storage_dir)
        self._entries: dict[str, MemoryEntry] = {}
        self._load_if_exists()

    @property
    def _file_path(self) -> Path:
        return self._storage_dir / "memory.json"

    def _load_if_exists(self) -> None:
        if self._file_path.exists():
            self.load()

    def add(self, category: MemoryCategory, content: str) -> MemoryEntry:
        entry = MemoryEntry(category=category, content=content)
        self._entries[entry.entry_id] = entry
        self.save()
        return entry

    def get(self, entry_id: str) -> MemoryEntry | None:
        return self._entries.get(entry_id)

    def list_entries(self, category: MemoryCategory | None = None) -> list[MemoryEntry]:
        entries = list(self._entries.values())
        if category is not None:
            entries = [e for e in entries if e.category == category]
        entries.sort(key=lambda e: e.created_at)
        return entries

    def delete(self, entry_id: str) -> bool:
        if entry_id in self._entries:
            del self._entries[entry_id]
            self.save()
            return True
        return False

    def clear(self) -> None:
        self._entries.clear()
        self.save()

    def search(self, query: str) -> list[MemoryEntry]:
        query_lower = query.lower()
        return [e for e in self._entries.values() if query_lower in e.content.lower()]

    def save(self) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        data = [_entry_to_dict(e) for e in self._entries.values()]
        self._file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self) -> None:
        if not self._file_path.exists():
            return
        try:
            data = json.loads(self._file_path.read_text(encoding="utf-8"))
            self._entries = {e["entry_id"]: _entry_from_dict(e) for e in data}
        except (json.JSONDecodeError, OSError, KeyError):
            self._entries = {}

    def to_prompt_text(self) -> str:
        """Generate text suitable for system prompt injection."""
        entries = self.list_entries()
        if not entries:
            return ""
        lines: list[str] = []
        by_cat: dict[MemoryCategory, list[MemoryEntry]] = {}
        for e in entries:
            by_cat.setdefault(e.category, []).append(e)
        for cat in MemoryCategory:
            cat_entries = by_cat.get(cat, [])
            if cat_entries:
                lines.append(f"[{cat.value}]")
                for e in cat_entries:
                    lines.append(f"- {e.content}")
        return "\n".join(lines)
