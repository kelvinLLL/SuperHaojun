"""Auto-extract memory entries from session summaries via LLM.

Usage:
    extracted = await extract_memories(summary_text, llm_fn)
    for mem in extracted:
        store.add(mem.category, mem.content, ...)
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from superhaojun.memory.store import MemoryCategory, MemoryEntry

EXTRACTION_SYSTEM_PROMPT = """\
You extract key facts and insights from a coding session summary.
Return a JSON array of objects, each with:
  - "category": one of "user", "feedback", "project", "reference"
  - "content": concise factual statement (1-2 sentences)
  - "name": short title (3-7 words)

Categories:
- user: user preferences, coding style, workflow habits
- feedback: corrections, mistakes to avoid, lessons learned
- project: project architecture, important file paths, conventions
- reference: API patterns, library usage, technical facts

Rules:
- Only extract durable facts, not transient details
- Skip tasks in progress or temporary state
- Max 5 items per extraction
- Return [] if nothing worth remembering

Return ONLY the JSON array, no markdown fences, no explanation."""

EXTRACTION_USER_PROMPT = """\
Session summary:
{summary}

Extract memory-worthy facts as a JSON array."""


async def extract_memories(
    summary: str,
    llm_fn: Callable[[str, str], Awaitable[str]],
) -> list[MemoryEntry]:
    """Extract memory entries from a session summary using an LLM.

    Args:
        summary: Session summary text.
        llm_fn: Async function(system_prompt, user_prompt) -> str response.

    Returns:
        List of MemoryEntry objects (not yet persisted).
    """
    if not summary.strip():
        return []
    user_prompt = EXTRACTION_USER_PROMPT.format(summary=summary)
    raw = await llm_fn(EXTRACTION_SYSTEM_PROMPT, user_prompt)

    # Parse JSON response, tolerant of markdown fences
    text = raw.strip()
    if text.startswith("```"):
        # Strip fences
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(items, list):
        return []

    entries: list[MemoryEntry] = []
    for item in items[:5]:  # Max 5
        if not isinstance(item, dict):
            continue
        content = item.get("content", "").strip()
        if not content:
            continue
        try:
            category = MemoryCategory(item.get("category", "user"))
        except ValueError:
            category = MemoryCategory.USER
        entries.append(
            MemoryEntry(
                category=category,
                content=content,
                name=item.get("name", content[:50]),
            )
        )
    return entries
