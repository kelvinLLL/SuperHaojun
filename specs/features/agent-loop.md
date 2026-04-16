---
title: Agent Loop
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/agent.py
  - src/superhaojun/bus.py
  - src/superhaojun/messages.py
  - src/superhaojun/permissions/checker.py
  - src/superhaojun/main.py
  - tests/test_agent.py
---

# Agent Loop

## Goal

- Drive one user turn from input to final assistant output.
- Support streamed text, tool calls, permission requests, and loop-back execution without tying the core flow to a specific UI transport.

## Scope

- In scope:
  - the `Agent.handle_user_message()` turn loop
  - message emission through `MessageBus`
  - structured message types used by the loop
  - permission gating before tool execution
  - CLI-side handler wiring needed for the default REPL flow
  - regression coverage for the core loop
- Out of scope:
  - prompt builder internals
  - tool implementation details
  - compactor summarization logic
  - hook implementation details
  - WebUI transport and presentation

## File Structure

- `src/superhaojun/agent.py`
  Responsibility: owns conversation state, builds outbound LLM requests, accumulates streamed deltas, detects tool calls, executes tools, and appends resulting assistant and tool messages.
- `src/superhaojun/bus.py`
  Responsibility: routes messages by type, deduplicates events, and provides request-response coordination through `expect()` and `wait_for()`.
- `src/superhaojun/messages.py`
  Responsibility: defines the serialized message contract shared between the agent loop and its consumers.
- `src/superhaojun/permissions/checker.py`
  Responsibility: resolves allow / ask / deny decisions from tool-name rules, risk-level rules, and default policy.
- `src/superhaojun/main.py`
  Responsibility: wires the default CLI consumer to the agent loop by registering render handlers and turning permission requests into user prompts plus `PermissionResponse` messages.
- `tests/test_agent.py`
  Responsibility: covers agent state handling, message building, streaming loop behavior, tool-call loop-back, and selected error cases.

## Current Design

- The agent loop is message-driven rather than iterator-driven. `Agent.handle_user_message()` appends the user message to in-memory history, emits `AgentStart` and `TurnStart`, then calls the OpenAI-compatible streaming API.
- Stream processing is split by payload type:
  - text chunks are appended to `text_chunks` and emitted as `TextDelta`
  - tool call fragments are accumulated by `tool_call.index` into `ToolCallInfo`
  - reasoning payloads are collected separately and stored on the final assistant message
- When the model finishes with `finish_reason == "tool_calls"`, the loop records the assistant tool-call message, executes all tool calls, appends tool results into history, and starts another model turn with the updated transcript.
- Tool execution is two-phase:
  - concurrent-safe tools run through `asyncio.gather()`
  - non-concurrent or unknown tools run sequentially
- Each tool execution goes through permission evaluation before the tool runs:
  - `PermissionChecker` defaults `read` tools to allow
  - `write` and `dangerous` tools default to ask
  - when the decision is ask, the agent creates a waiter with `bus.expect()` before emitting `PermissionRequest`
- Hooks can intercept the turn at four agent-loop boundaries that matter here:
  - `USER_PROMPT_SUBMIT`
  - `PRE_TOOL_USE`
  - `POST_TOOL_USE`
  - `STOP`
  Compaction hooks run after the main turn completes if auto-compaction triggers.
- The default CLI path is a thin consumer over this loop:
  - `main.py` registers bus handlers for text rendering, tool start/end rendering, error printing, and interactive permission approval
  - the REPL passes plain user input into `Agent.handle_user_message()`
- The core design goal is transport independence. The loop depends on `MessageBus` and structured messages, not on the terminal directly. This is what makes the same loop usable from both CLI and WebUI consumers.

## Open Questions

- Reasoning deltas are currently appended without normalizing type. The current test suite shows a regression when mocked stream objects expose a non-string `delta.reasoning`, so future work on this feature should decide whether the loop should coerce reasoning payloads to `str` or ignore non-string values.

## Verification

- Run `uv run pytest tests/test_agent.py -v` for focused loop coverage.
- Run `uv run pytest tests -q` before claiming broader safety, because the agent loop sits on several shared contracts used by other subsystems.
- Confirm these behaviors when editing the loop:
  - text-only turns emit `AgentStart` → `TurnStart` → `TextDelta*` → `TurnEnd` → `AgentEnd`
  - tool-call turns append `assistant(tool_calls)` then `tool` then final `assistant`
  - permission requests always install the waiter before emitting `PermissionRequest`
  - CLI permission prompts still round-trip into `PermissionResponse`

## Follow-ups

- Create separate feature specs for `hooks-runtime`, `prompt-context`, and `webui-chat` so future changes stop overloading this file with adjacent subsystem decisions.
- If the reasoning regression is fixed, record the chosen normalization rule here and keep the verification section aligned with the updated tests.
