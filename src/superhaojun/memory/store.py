"""MemoryStore v2 — Markdown-based cross-session persistent memory.

Storage format:
  .haojun/memory/
  ├── MEMORY.md         # Index file (auto-generated)
  ├── user_*.md         # Individual memory files with frontmatter
  ├── feedback_*.md
  ├── project_*.md
  └── reference_*.md

Each memory file:
  ---
  name: <title>
  description: <brief description>
  type: <user|feedback|project|reference>
  id: <uuid>
  created_at: <float timestamp>
  ---
  <content>

Backward compatibility: auto-migrates legacy memory.json to markdown format.
"""

from __future__ import annotations

import json
import re
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
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            # Auto-generate name from content (first 50 chars, sanitized)
            preview = self.content[:50].strip().replace("\n", " ")
            object.__setattr__(self, "name", preview) if hasattr(self, "__dataclass_fields__") else None
            self.name = preview


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)", re.DOTALL)


def _entry_to_markdown(entry: MemoryEntry) -> str:
    """Serialize a MemoryEntry to markdown with frontmatter."""
    return (
        f"---\n"
        f"name: {entry.name}\n"
        f"description: {entry.description}\n"
        f"type: {entry.category.value}\n"
        f"id: {entry.entry_id}\n"
        f"created_at: {entry.created_at}\n"
        f"---\n"
        f"{entry.content}\n"
    )


def _entry_from_markdown(text: str) -> MemoryEntry | None:
    """Parse a MemoryEntry from markdown with frontmatter."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    frontmatter_text, content = match.groups()

    meta: dict[str, str] = {}
    for line in frontmatter_text.strip().split("\n"):
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()

    try:
        category = MemoryCategory(meta.get("type", "user"))
    except ValueError:
        category = MemoryCategory.USER

    return MemoryEntry(
        category=category,
        content=content.strip(),
        entry_id=meta.get("id", uuid4().hex),
        created_at=float(meta.get("created_at", 0)),
        name=meta.get("name", ""),
        description=meta.get("description", ""),
    )


def _safe_filename(entry: MemoryEntry) -> str:
    """Generate filesystem-safe filename from entry."""
    slug = re.sub(r"[^a-z0-9]+", "_", entry.name.lower())[:30].strip("_")
    if not slug:
        slug = entry.entry_id[:8]
    return f"{entry.category.value}_{slug}_{entry.entry_id[:8]}.md"


class MemoryStore:
    """Persistent memory store backed by markdown files.

    Reads/writes individual .md files in storage_dir.
    Maintains a MEMORY.md index file.
    Auto-migrates from legacy memory.json if found.
    """

    def __init__(self, storage_dir: Path | str) -> None:
        self._storage_dir = Path(storage_dir)
        self._entries: dict[str, MemoryEntry] = {}
        self._migrate_legacy()
        self._load_all()

    @property
    def _index_path(self) -> Path:
        return self._storage_dir / "MEMORY.md"

    @property
    def _legacy_path(self) -> Path:
        return self._storage_dir / "memory.json"

    def _migrate_legacy(self) -> None:
        """Auto-migrate legacy memory.json to markdown if it exists."""
        if not self._legacy_path.exists():
            return
        try:
            data = json.loads(self._legacy_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            for item in data:
                entry = MemoryEntry(
                    entry_id=item.get("entry_id", uuid4().hex),
                    category=MemoryCategory(item.get("category", "user")),
                    content=item.get("content", ""),
                    created_at=item.get("created_at", 0),
                )
                self._write_entry(entry)
            # Remove legacy file after migration
            self._legacy_path.unlink()
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            pass

    def _load_all(self) -> None:
        """Load all .md memory files from storage directory."""
        self._entries.clear()
        if not self._storage_dir.exists():
            return
        for path in sorted(self._storage_dir.glob("*.md")):
            if path.name == "MEMORY.md":
                continue
            entry = _entry_from_markdown(path.read_text(encoding="utf-8"))
            if entry:
                self._entries[entry.entry_id] = entry

    def add(self, category: MemoryCategory, content: str, name: str = "", description: str = "") -> MemoryEntry:
        entry = MemoryEntry(
            category=category,
            content=content,
            name=name or content[:50].strip().replace("\n", " "),
            description=description,
        )
        self._entries[entry.entry_id] = entry
        self._write_entry(entry)
        self._write_index()
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
        entry = self._entries.pop(entry_id, None)
        if entry is None:
            return False
        # Remove the .md file
        for path in self._storage_dir.glob("*.md"):
            if path.name == "MEMORY.md":
                continue
            text = path.read_text(encoding="utf-8")
            if f"id: {entry_id}" in text:
                path.unlink()
                break
        self._write_index()
        return True

    def clear(self) -> None:
        self._entries.clear()
        if self._storage_dir.exists():
            for path in self._storage_dir.glob("*.md"):
                path.unlink()

    def search(self, query: str) -> list[MemoryEntry]:
        query_lower = query.lower()
        return [e for e in self._entries.values() if query_lower in e.content.lower()]

    def save(self) -> None:
        """Write all entries to disk (full sync)."""
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        for entry in self._entries.values():
            self._write_entry(entry)
        self._write_index()

    def load(self) -> None:
        """Reload all entries from disk."""
        self._load_all()

    def to_prompt_text(self) -> str:
        """Generate text for system prompt injection, grouped by category."""
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

    def _write_entry(self, entry: MemoryEntry) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        filename = _safe_filename(entry)
        path = self._storage_dir / filename
        path.write_text(_entry_to_markdown(entry), encoding="utf-8")

    def _write_index(self) -> None:
        """Regenerate MEMORY.md index file."""
        if not self._entries:
            if self._index_path.exists():
                self._index_path.unlink()
            return
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        lines = ["# Memory Index\n"]
        by_cat: dict[MemoryCategory, list[MemoryEntry]] = {}
        for e in self._entries.values():
            by_cat.setdefault(e.category, []).append(e)
        for cat in MemoryCategory:
            cat_entries = by_cat.get(cat, [])
            if cat_entries:
                lines.append(f"\n## {cat.value.title()}\n")
                for e in sorted(cat_entries, key=lambda x: x.created_at):
                    filename = _safe_filename(e)
                    desc = e.description or e.content[:80].replace("\n", " ")
                    lines.append(f"- [{e.name}]({filename}) — {desc}")
        self._index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
