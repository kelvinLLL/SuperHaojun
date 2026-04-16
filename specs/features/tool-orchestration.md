---
title: Tool Orchestration
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/agent.py
  - src/superhaojun/tool_orchestration.py
  - src/superhaojun/tools/base.py
  - src/superhaojun/tools/registry.py
  - src/superhaojun/permissions/checker.py
  - src/superhaojun/hooks/runner.py
  - tests/test_agent.py
  - tests/test_tool_orchestration.py
---

# Tool Orchestration

## Goal

- Define how tool calls are batched, executed, gated, and recorded once the model asks to use tools.
- Separate tool execution runtime behavior from the main agent loop so new control features can evolve without further inflating `agent.py`.

## Scope

- In scope:
  - tool-call batch construction after streaming completes
  - concurrent versus sequential execution policy
  - permission checks before execution
  - pre and post tool hook integration
  - tool-result recording back into the transcript
  - runtime state that explains which tools are pending, running, blocked, or finished
- Out of scope:
  - tool implementation code
  - generic message-bus routing
  - MCP server lifecycle
  - prompt building

## File Structure

- `src/superhaojun/agent.py`
  Responsibility: currently owns tool-call buffering and assistant/tool transcript recording, and is the caller that should delegate execution behavior into a dedicated orchestration boundary.
- `src/superhaojun/tool_orchestration.py`
  Responsibility: implementation target for extracted tool execution policy, permission gating, hook wrapping, and result production.
- `src/superhaojun/tools/base.py`
  Responsibility: defines the tool metadata that orchestration reads today, especially concurrency and risk hints.
- `src/superhaojun/tools/registry.py`
  Responsibility: provides name-based lookup and tool export, making it the capability source used by orchestration.
- `src/superhaojun/permissions/checker.py`
  Responsibility: resolves whether a tool should auto-run, ask, or deny before orchestration calls it.
- `src/superhaojun/hooks/runner.py`
  Responsibility: exposes the pre and post tool hook boundaries that currently wrap individual tool execution.
- `tests/test_agent.py`
  Responsibility: verifies the visible behavior of tool execution inside the current agent-loop implementation.

## Current Design

- The repo now has a dedicated orchestration module in `src/superhaojun/tool_orchestration.py`.
- The current flow is:
  - accumulate streamed tool-call fragments by index
  - detect `finish_reason == "tool_calls"`
  - record the assistant tool-call message
  - delegate tool execution to `ToolOrchestrator`
  - partition tool calls into concurrent-safe and sequential groups
  - run each tool through permission and hook boundaries
  - append normalized tool results into transcript history
  - loop back into the next model turn
- The current scheduling rule is intentionally simple:
  - tools whose metadata says `is_concurrent_safe` run through `asyncio.gather()`
  - all other tools run sequentially
- `ToolOrchestrator` now owns:
  - concurrent versus sequential grouping
  - per-tool permission gating
  - pre and post hook execution
  - `ToolCallStart` and `ToolCallEnd` emission
  - normalization of tool results into a dedicated result object
- `Agent` still owns:
  - tool-call buffering during streaming
  - assistant tool-call transcript append
  - appending final tool messages into the conversation transcript
- Tool runtime state is now partially explicit through `turn-runtime`. Users can observe emitted start and end events, and the harness now records per-tool status such as `pending`, `running`, `blocked`, `completed`, and `failed` in shared runtime state during execution.
- This extraction intentionally preserves the raw user-visible event stream and permission semantics instead of introducing summaries or hidden orchestration layers.

## Open Questions

- Whether tool execution should eventually produce structured runtime updates in addition to transcript messages, so WebUI and other frontends can render queue state without inferring it indirectly.
- Whether argument validation should become part of orchestration before tool `execute()` is called, instead of staying distributed across tool code.

## Verification

- Run `uv run pytest tests/test_tool_orchestration.py -v`.
- Run `uv run pytest tests/test_agent.py -v`.
- Run `uv run pytest tests/test_tools.py -v`.
- When changing this feature later, confirm that:
  - concurrent-safe tools still batch correctly
  - sequential tools still preserve execution order
  - permission requests are emitted before gated tools run
  - hook rewrites and hook-added context still affect tool results as expected

## Follow-ups

- Continue aligning this feature with `turn-runtime` so current per-tool status can evolve into a richer batch-level execution model instead of stopping at flat status entries.
- Keep `tool-system` focused on capability declaration and let this feature own execution policy.
