---
title: Context Compaction
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/compact/compactor.py
  - src/superhaojun/compact/prompts.py
  - src/superhaojun/compact/session_compact.py
  - src/superhaojun/agent.py
  - tests/test_compact.py
---

# Context Compaction

## Goal

- Shrink long conversations before they exceed the model context window.
- Preserve enough recent and summarized context that the agent can continue working coherently after compaction.

## Scope

- In scope:
  - token estimation
  - compaction threshold logic
  - structured compaction prompt text
  - circuit-breaker cooldown
  - session-summary compaction helpers
  - agent-side replacement of compacted history
- Out of scope:
  - the prompt builder section registry
  - session persistence storage format
  - memory extraction policy

## File Structure

- `src/superhaojun/compact/compactor.py`
  Responsibility: estimates token usage, decides when to compact, runs summarization, and returns replacement metadata.
- `src/superhaojun/compact/prompts.py`
  Responsibility: stores the structured prompts used for conversation and session compaction.
- `src/superhaojun/compact/session_compact.py`
  Responsibility: provides session-level summary helpers that sit adjacent to the main compactor flow.
- `src/superhaojun/agent.py`
  Responsibility: triggers auto-compaction, replaces the in-memory message list, and invalidates prompt cache afterward.
- `tests/test_compact.py`
  Responsibility: verifies token estimation, prompt shape, circuit breaker behavior, and compaction output rules.

## Current Design

- `ContextCompactor` uses a rough `len(text) // 4` token estimate. The threshold is based on `max_tokens * compact_threshold`.
- When compaction runs:
  - the recent tail defined by `preserve_recent` is kept verbatim
  - older messages are flattened into a single text transcript
  - `summarize_fn` is called with a structured prompt
  - the summary output is capped to `max_tokens * 0.3`
- The cooldown-based circuit breaker prevents repeated compactions in a tight loop after a recent summary has already been produced.
- `CompactionResult.to_messages()` emits a single synthetic system summary message. The caller is responsible for appending preserved recent messages afterward.
- The agent loop only mutates history after compaction succeeds, then invalidates the prompt builder so the new summary boundary is reflected in future prompt assembly.

## Open Questions

- The default summarizer is intentionally a stub. Production-quality compaction depends on the injected `summarize_fn`, so future optimization needs to decide whether compaction should own a richer built-in LLM path or remain a thin orchestration layer.

## Verification

- Run `uv run pytest tests/test_compact.py -v`.
- Manually verify `/compact` in the CLI if compaction behavior changes.
- When editing compaction logic, confirm:
  - cooldown still prevents duplicate compactions
  - preserved recent messages remain intact
  - summary messages still replace the compacted prefix rather than appending duplicate history
  - prompt cache invalidation still happens after auto-compaction

## Follow-ups

- If token accounting becomes provider-specific, move beyond `chars / 4` estimation without mixing that concern into unrelated prompt-building code.
