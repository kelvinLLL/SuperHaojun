---
title: Memory Entry
status: active
owner: Haojun
last_updated: 2026-04-16
source_paths:
  - src/superhaojun/memory/store.py
  - src/superhaojun/prompt/sections/memory.py
  - src/superhaojun/prompt/builder.py
  - src/superhaojun/runtime.py
  - src/superhaojun/commands/builtins.py
  - src/superhaojun/turn_runtime.py
  - tests/test_memory.py
  - tests/test_prompt.py
---

# Memory Entry

## Goal

- Define how durable memory enters prompt context in a bounded, inspectable way.
- Keep local memory useful over time without letting prompt injection silently expand into an opaque blob.

## Scope

- In scope:
  - memory entrypoint design for prompt injection
  - relationship between `MEMORY.md`, individual memory files, and prompt text
  - bounded loading and truncation rules
  - visibility into which memory content or indexes were injected for a turn
- Out of scope:
  - memory extraction policy
  - remote sync
  - ranking across teammates or devices

## File Structure

- `src/superhaojun/memory/store.py`
  Responsibility: persists memory files, maintains `MEMORY.md`, and defines the bounded prompt-entry export used by runtime wiring.
- `src/superhaojun/prompt/sections/memory.py`
  Responsibility: injects memory into the prompt and adds guidance about stale memory usage.
- `src/superhaojun/prompt/builder.py`
  Responsibility: carries the current memory entry text plus injection metadata into prompt assembly and exposes that metadata to the runtime.
- `src/superhaojun/runtime.py`
  Responsibility: wires the shared runtime to use the store's bounded memory entry export instead of unbounded full-text export.
- `src/superhaojun/commands/builtins.py`
  Responsibility: refreshes prompt memory entry after `/memory` mutations so prompt state does not drift behind persisted memory.
- `src/superhaojun/turn_runtime.py`
  Responsibility: exposes the memory entry summary used for the active turn so durable context influence is inspectable.
- `tests/test_memory.py`
  Responsibility: verifies memory persistence plus bounded prompt-entry export behavior.
- `tests/test_prompt.py`
  Responsibility: verifies prompt-builder handling of memory entry text and metadata.

## Current Design

- `MemoryStore` now exports a structured `MemoryPromptEntry` instead of treating prompt entry as raw flattened memory text.
- The shipped prompt-entry path is:
  - render the same category-oriented index shape as `MEMORY.md`
  - remove file-link noise from the prompt version of the index
  - add a bounded expansion of the most recent topic entries
  - enforce character budgets separately for index text and topic snippets
- `MemoryStore.to_prompt_text()` remains available for compatibility, but now delegates to the bounded entry export instead of unbounded category dumps.
- Prompt-entry metadata now travels with the exported text:
  - loaded entry ids, names, categories, and source filenames
  - whether truncation happened
  - index, topic, and total character counts
- `SystemPromptBuilder` now carries both memory text and memory-entry metadata, so the prompt section still consumes one string while runtime state can inspect the underlying entry summary.
- The shared runtime now initializes prompt memory from `build_prompt_entry()` instead of `to_prompt_text()`, and `/memory add` plus `/memory delete` refresh that entry immediately.
- `TurnRuntimeState` now includes the active `memory_entry` metadata snapshot, so durable memory influence is visible as runtime state instead of hidden prompt-builder input.

## Open Questions

- This slice resolves the main budget decision in favor of character-based limits for simplicity. If future retrieval needs become more model-sensitive, token-aware budgeting can be layered on top later.

## Verification

- Run `uv run pytest tests/test_memory.py -v`.
- Run prompt/runtime tests that cover memory entry metadata and refresh behavior.
- When changing this feature later, confirm that:
  - `MEMORY.md` remains a stable index artifact
  - prompt entry stays bounded as memory volume grows
  - users can still inspect what memory content influenced a run
  - storage format changes do not reintroduce legacy migration risk

## Follow-ups

- Keep `memory-store` focused on persistence and extraction concerns, and let this feature own prompt-entry policy.
- Revisit prompt entry after `turn-runtime` exists, so injected memory can be surfaced as explicit runtime state instead of hidden builder input.
