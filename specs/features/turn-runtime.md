---
title: Turn Runtime
status: active
owner: Haojun
last_updated: 2026-04-17
source_paths:
  - src/superhaojun/agent.py
  - src/superhaojun/turn_runtime.py
  - src/superhaojun/tool_orchestration.py
  - src/superhaojun/compact/compactor.py
  - src/superhaojun/webui/server.py
  - src/superhaojun/messages.py
  - tests/test_agent.py
  - tests/test_messages.py
  - tests/test_turn_runtime.py
  - tests/test_compact.py
---

# Turn Runtime

## Goal

- Define the per-turn runtime state used to drive one agent turn from user input through model calls, tool execution, and completion.
- Make runtime state explicit and user-visible instead of leaving important control data hidden inside local variables.

## Scope

- In scope:
  - immutable per-turn config and mutable per-turn state
  - turn lifecycle boundaries such as start, streaming, tool phase, stop, interrupt, and post-turn bookkeeping
  - runtime counters and status values exposed to WebUI or other consumers
  - state needed for future retry, interrupt, budget, and resume work
- Out of scope:
  - durable transcript ownership
  - tool implementation code
  - frontend-specific presentation
  - remote bridge or reconnect infrastructure

## File Structure

- `src/superhaojun/agent.py`
  Responsibility: currently owns turn control flow and should update a dedicated runtime-state object instead of keeping the key state only in locals.
- `src/superhaojun/turn_runtime.py`
  Responsibility: owns the named runtime snapshot, including phase, queue state, token estimates, and compaction metadata that frontends and tests should be able to inspect directly.
- `src/superhaojun/tool_orchestration.py`
  Responsibility: should report tool execution state transitions back into the shared turn runtime instead of leaving queue semantics implicit in event order.
- `src/superhaojun/compact/compactor.py`
  Responsibility: provides the token and compaction metadata that runtime state should surface rather than forcing WebUI to derive those counters independently.
- `src/superhaojun/webui/server.py`
  Responsibility: should expose the shared turn runtime snapshot instead of only derived token estimates.
- `src/superhaojun/messages.py`
  Responsibility: defines the event envelope used to expose major turn boundaries to consumers.
- `tests/test_agent.py`
  Responsibility: verifies visible turn sequencing and loop-back behavior.
- `tests/test_messages.py`
  Responsibility: protects the structured event contract that future runtime-state exposure will continue to rely on.

## Current Design

- The repo now has a structured runtime object in `src/superhaojun/turn_runtime.py`.
- `TurnRuntimeState` currently captures:
  - `turn_index`
  - `phase`
  - `model_id`
  - `finish_reason`
  - streamed text chunks
  - streamed reasoning chunks
  - buffered tool calls
  - explicit tool queue status entries
  - transcript-level message and token counters
  - prompt-context metrics derived from the actual assembled request
  - provider-usage metadata returned by the upstream model API
  - current-turn text and reasoning token estimates
  - compaction counters and last-compaction metadata
  - active memory-entry metadata for the current prompt build
  - active and timing state
- `TurnRuntimeState` is also the right boundary for user-visible usage accounting:
  - transcript-level rough estimates may stay here as internal runtime counters
  - real provider usage, when returned by the model API, should also be stored here instead of being dropped before the WebUI sees it
  - prompt/context accounting derived from the actual assembled request should be exposed alongside transcript counters so users can see what the harness truly sent
- `Agent` now updates `turn_runtime` as each LLM turn progresses:
  - `start_turn()` at the top of each looped API call
  - prompt-context metric snapshotting during `_build_messages()` before the request leaves the process
  - incremental text and reasoning chunk recording during stream processing
  - provider-usage capture from streaming chunk metadata when the upstream SDK supplies usage counts
  - buffered tool-call snapshot updates while tool call fragments accumulate
  - transcript-level metric refresh after user, assistant, tool, and hook-context messages
  - `tool_execution` phase when a turn ends in tool calls
  - `completed` phase when a turn ends normally
- `ToolOrchestrator` now feeds explicit queue transitions back into the shared runtime:
  - `pending` when a tool batch is prepared
  - `running` when a concrete tool starts
  - `completed` when a tool returns normally
  - `blocked` when permission or hooks prevent execution
  - `failed` when argument parsing, lookup, or execution errors prevent a clean success path
- Compaction now also reports into runtime state:
  - `compaction_pending` is derived from the current transcript size
  - `compaction_count` increments after each successful replacement
  - `last_compaction` records removed count plus pre/post token estimates
- Prompt entry now also reports into runtime state:
  - `SystemPromptBuilder` exposes memory-entry metadata alongside memory text
  - `Agent._build_messages()` snapshots that metadata into `turn_runtime`
  - users can inspect which durable memory entries influenced a turn without reading the entire system prompt
- Some runtime state is exposed today, but only partially:
  - bus events expose turn and tool lifecycle
  - WebUI token usage now reads from the shared runtime counters instead of maintaining a separate rough estimate
  - WebUI init payload now includes a `runtime` snapshot
  - WebUI now has a dedicated `/api/runtime` endpoint
  - WebUI also forwards `runtime_state` snapshots alongside the existing raw event stream
  - model changes are broadcast explicitly
  - interrupt exists as a message type but is not wired end to end
- This means users can now inspect queue and counter state without inferring it only from text deltas or WebUI-specific helper math, and recent optimization work tightened the contract further:
  - prompt/context contribution accounting is now surfaced as first-class runtime data
  - provider usage is now preserved when the upstream API supplies real counts
  - prompt-context metrics remain visible even if the later provider call fails
  - interruption state is still not wired as a richer resumable state machine
  - queue state is explicit during execution, but not yet modeled as a richer long-lived batch object
- The active optimization direction remains to borrow the `QueryConfig / state snapshot` idea from Claude Code in a lighter Python form, so immutable turn config and mutable turn state stop being mixed together.
- This feature is also the main place where `Explainability First` becomes concrete. Runtime state should be exposed because it helps users understand what the harness is doing, not merely because it helps debugging.

## Open Questions

- Whether compaction and token-budget tracking should live inside the same turn runtime object or in adjacent runtime helpers that report into it.
- Whether interrupt should be represented as a turn-state transition, a bus-only control message, or both.

## Verification

- Run `uv run pytest tests/test_agent.py -v`.
- Run `uv run pytest tests/test_messages.py -v`.
- When changing this feature later, confirm that:
  - visible turn sequencing remains stable
  - runtime counters shown to users still correspond to real internal state
  - provider usage does not regress to rough estimates when the upstream API supplied real counts
  - prompt/context counters correspond to the actual assembled request, not UI-side approximations
  - prompt/context counters are still available on provider-side failures
  - interrupt and future resume work do not require re-hiding state that was previously visible

## Follow-ups

- Align this feature with `runtime-assembly` so all frontends consume the same runtime-state source.
- Align this feature with `tool-orchestration` so tool queues and blocked states become part of shared turn state instead of frontend inference.
