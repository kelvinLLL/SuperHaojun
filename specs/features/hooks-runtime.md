---
title: Hooks Runtime
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/hooks/config.py
  - src/superhaojun/hooks/runner.py
  - src/superhaojun/agent.py
  - tests/test_hooks.py
---

# Hooks Runtime

## Goal

- Let external rules and internal callbacks intercept important lifecycle events.
- Support blocking, input rewriting, and context injection without hard-coding those behaviors into the agent loop.

## Scope

- In scope:
  - hook events and hook rule types
  - registry matching and persistence
  - command and function hook execution
  - aggregated hook semantics
  - current agent-loop integration points
- Out of scope:
  - hook authoring UI
  - file watchers or environment emitters that have not yet been wired in
  - external policy systems beyond local hook config

## File Structure

- `src/superhaojun/hooks/config.py`
  Responsibility: defines hook events, rules, contexts, result objects, and registry load/save behavior.
- `src/superhaojun/hooks/runner.py`
  Responsibility: matches hooks, executes command or function hooks, parses structured stdout, and returns aggregated semantics.
- `src/superhaojun/agent.py`
  Responsibility: invokes hooks at user-submit, pre-tool, post-tool, stop, and compaction boundaries.
- `tests/test_hooks.py`
  Responsibility: verifies event definitions, matching, result aggregation, registry behavior, and runner execution paths.

## Current Design

- Hooks are defined around lifecycle `HookEvent` values. Events include session, prompt submission, tool execution, stop, compaction, sub-agent, and environment-change categories.
- Two hook types exist:
  - `command`
  - `function`
- `HookRegistry` merges persistent config rules with runtime-added rules and sorts matches by ascending priority.
- `HookRunner.run_hooks()` executes all matching hooks in parallel for a given event and returns one `AggregatedHookResult`.
- Structured hook semantics are centralized:
  - `exit_code == 2` means blocking
  - `additional_context` appends information back into the agent flow
  - `updated_input` lets hooks rewrite tool arguments or prompt input
- Command hooks can emit JSON on stdout to return structured results. Function hooks can return either plain output or dict-shaped structured responses.
- The most important current integrations are in `Agent.handle_user_message()` and `_run_one_tool()`, where hooks can block input, rewrite arguments, attach post-tool context, or inspect final assistant output.

## Open Questions

- The config layer defines more lifecycle events than are currently emitted by the runtime. As future integrations land, keep this spec aligned with which events are merely modeled versus actually wired.

## Verification

- Run `uv run pytest tests/test_hooks.py -v`.
- When changing agent integration points, also run `uv run pytest tests/test_agent.py -v`.
- Confirm these behaviors after edits:
  - blocking hooks still stop the underlying operation
  - `updated_input` still follows last-wins semantics
  - `additional_context` still flows back into the agent output path
  - command-hook JSON parsing remains tolerant of plain-text stdout

## Follow-ups

- If hook integrations spread beyond the agent loop, add emitters carefully rather than making `HookRunner` responsible for discovering lifecycle changes on its own.
