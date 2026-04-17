---
title: Prompt Context
status: active
owner: Haojun
last_updated: 2026-04-17
source_paths:
  - src/superhaojun/prompt/builder.py
  - src/superhaojun/prompt/context.py
  - src/superhaojun/prompt/sections
  - src/superhaojun/extensions/runtime.py
  - src/superhaojun/constants.py
  - tests/test_prompt.py
---

# Prompt Context

## Goal

- Build the system prompt from modular sections instead of a monolithic string builder.
- Keep stable prompt content separate from per-turn dynamic context.

## Scope

- In scope:
  - `SystemPromptBuilder`
  - `PromptContext` and `GitInfo`
  - prompt section registration and ordering
  - project instruction discovery
  - memory and session-summary injection
- Out of scope:
  - the agent loop that consumes the final prompt
  - compaction summarization logic
  - memory extraction and persistence internals

## File Structure

- `src/superhaojun/prompt/builder.py`
  Responsibility: assembles the full prompt from ordered sections and handles cache invalidation.
- `src/superhaojun/prompt/context.py`
  Responsibility: defines the shared build-time context and collects git metadata.
- `src/superhaojun/prompt/sections/*.py`
  Responsibility: each file contributes one prompt section such as identity, tools, environment, project instructions, memory, or session context.
- `src/superhaojun/extensions/runtime.py`
  Responsibility: discovers prompt-capable repo-local extensions and provides the metadata that prompt sections render.
- `src/superhaojun/constants.py`
  Responsibility: holds prompt-related brand constants such as `BRAND_DIR`, `INSTRUCTION_FILES`, and the dynamic boundary marker.
- `tests/test_prompt.py`
  Responsibility: verifies section behavior, recursive instruction discovery, context defaults, and prompt assembly rules.

## Current Design

- `SystemPromptBuilder` uses a section registry instead of hard-coded string concatenation.
- Default section order is:
  - identity
  - tools
  - project instructions
  - custom instructions
  - environment
  - memory
  - session context
- Sections declare whether they are cacheable. The builder inserts `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` before uncacheable sections so prompt consumers can distinguish stable and dynamic regions.
- `PromptContext` is rebuilt on each `build()` call and carries:
  - working directory
  - tool summaries
  - memory text
  - loaded repo-local extension entries
  - custom instructions
  - git info
  - session summary
- `SystemPromptBuilder` now owns a shared `ExtensionRuntime` by default, so prompt assembly can reuse one discovered repo-local extension view instead of rediscovering instructions ad hoc on every integration surface.
- `ProjectInstructionsSection` now renders loaded prompt-capable repo-local extensions when they are present in `PromptContext`. Direct section usage still falls back to recursive filesystem discovery for plain instruction files.
- Repo-local prompt extensions currently include:
  - recursive instruction files from the current working directory up to filesystem root
  - `specs/development-rules.md` when it exists in the active repo tree
- `set_memory_text()` and `set_session_summary()` invalidate the full prompt cache so downstream consumers always see updated dynamic context.
- Prompt assembly should expose explainable accounting data in addition to raw text:
  - the runtime should be able to report the assembled system prompt length shown to the model
  - the runtime should also be able to break that prompt down into major contributors such as tools, repo-local extensions, memory, and session summary when those sections are present
  - this accounting is for user-visible harness observability, so it should describe the actual assembled prompt boundary instead of only a rough transcript token estimate
- `SystemPromptBuilder.build_metrics()` is now the contract used by the runtime for that accounting:
  - it reports total assembled prompt chars
  - it reports section-by-section char counts plus cacheable or dynamic metadata
  - it reports dedicated contributor buckets such as memory, session summary, custom instructions, and extension prompt text
- This accounting must be available before the upstream provider responds:
  - request assembly happens before any model API call
  - prompt-context metrics therefore remain inspectable even when the provider later returns a `404`, `429`, or other transport failure
  - user-visible harness observability should still show what the harness attempted to send in those failure cases
- Repo-local extensions must stay attributable in that accounting:
  - disabling an extension must remove both its prompt text and its reported prompt contribution
  - prompt-capable extension metadata should remain inspectable even when disabled so users can understand why prompt length changed

## Open Questions

- `SystemPromptBuilder` still has a `_cached_static` field, but current assembly only uses `_cached_full`. If later optimization wants true static/dynamic cache reuse, this file is the boundary that should own that cleanup or expansion.

## Verification

- Run `uv run pytest tests/test_prompt.py -v`.
- When changing section order or instruction discovery, confirm:
  - ancestor instruction files still appear before local ones
  - `.haojun/` instructions are still discovered
  - loaded repo-local extensions appear in prompt output when enabled
  - disabled repo-local extensions do not reappear through fallback discovery
  - memory and session summary updates invalidate the prompt
  - prompt/context accounting reflects the actual built prompt after invalidation
  - prompt/context accounting still exists even when the later provider call fails
  - the dynamic boundary marker still separates stable and per-turn content

## Follow-ups

- If prompt sections keep growing, add separate feature specs for high-churn sections rather than turning this file into a second architecture essay.
