---
title: Memory Store
status: active
owner: Haojun
last_updated: 2026-04-16
source_paths:
  - src/superhaojun/memory/store.py
  - src/superhaojun/memory/extractor.py
  - src/superhaojun/runtime.py
  - tests/test_memory.py
---

# Memory Store

## Goal

- Preserve durable user, project, feedback, and reference facts across sessions.
- Format those memories so they can be re-injected into future prompts.

## Scope

- In scope:
  - markdown-backed memory storage
  - memory indexing
  - legacy migration from JSON
  - prompt-text generation
  - LLM-driven memory extraction from summaries
- Out of scope:
  - prompt section assembly
  - long-term ranking or decay policy
  - sync across machines or teammates

## File Structure

- `src/superhaojun/memory/store.py`
  Responsibility: defines `MemoryCategory`, `MemoryEntry`, markdown serialization, file persistence, index regeneration, bounded prompt-entry export, and backward-compatible prompt text helpers.
- `src/superhaojun/memory/extractor.py`
  Responsibility: turns a session summary into candidate `MemoryEntry` objects through an LLM-facing extraction prompt.
- `src/superhaojun/runtime.py`
  Responsibility: initializes the store inside shared runtime assembly and wires the bounded prompt entry into the prompt builder.
- `tests/test_memory.py`
  Responsibility: verifies CRUD behavior, markdown round-trips, legacy migration, indexing, and extraction helpers.

## Current Design

- Each memory entry is stored as its own Markdown file with front matter for:
  - name
  - description
  - type
  - id
  - created timestamp
- `MEMORY.md` is regenerated as an index file summarizing the stored entries by category.
- The store groups entries into four categories:
  - user
  - feedback
  - project
  - reference
- `MemoryStore` now exposes a bounded `MemoryPromptEntry` export that reuses the `MEMORY.md` index structure plus limited recent-topic expansion.
- `MemoryStore.to_prompt_text()` remains as a compatibility method, but it now delegates to the bounded prompt-entry path owned by `memory-entry`.
- `extract_memories()` is intentionally tolerant:
  - it accepts fenced JSON responses
  - it ignores malformed items
  - it caps output to five entries
  - it returns entries without persisting them, leaving persistence to the caller
- Legacy `memory.json` is auto-migrated into Markdown entry files the next time the store loads.

## Open Questions

- Memory extraction is available as a helper, but the current runtime wiring does not yet make automatic extraction a guaranteed end-of-session behavior. If future optimization wants memory to become more proactive, this feature boundary should own that orchestration.

## Verification

- Run `uv run pytest tests/test_memory.py -v`.
- When changing storage behavior, confirm:
  - per-entry Markdown files still round-trip cleanly
  - `MEMORY.md` is regenerated when entries change
  - legacy `memory.json` still migrates safely
  - bounded prompt-entry export still reflects stored entries without leaking unbounded content

## Follow-ups

- Keep prompt-entry policy in `memory-entry` instead of turning `MemoryStore` into both storage and retrieval policy.
- If memory volume grows large, split retrieval and storage concerns before turning `MemoryStore` into both a database and a ranking engine.
