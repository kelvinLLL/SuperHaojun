---
title: Command System
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/commands/base.py
  - src/superhaojun/commands/registry.py
  - src/superhaojun/commands/builtins.py
  - src/superhaojun/main.py
  - src/superhaojun/mcp/commands.py
  - src/superhaojun/agents/commands.py
  - tests/test_commands.py
---

# Command System

## Goal

- Provide non-LLM control paths for local operator actions.
- Keep slash commands lightweight and composable so the REPL and WebUI can share the same command surface.

## Scope

- In scope:
  - slash command abstraction
  - registry lookup and prefix completion
  - built-in commands
  - REPL-side command interception
  - command metadata reuse in WebUI autocomplete
- Out of scope:
  - natural-language agent turns
  - tool-call execution
  - command persistence or undo history

## File Structure

- `src/superhaojun/commands/base.py`
  Responsibility: defines the `Command` interface and the shared `CommandContext`.
- `src/superhaojun/commands/registry.py`
  Responsibility: stores commands, supports lookup, and returns completion candidates.
- `src/superhaojun/commands/builtins.py`
  Responsibility: implements the built-in local commands such as `/help`, `/clear`, `/compact`, `/model`, `/session`, and `/tools`.
- `src/superhaojun/mcp/commands.py`
  Responsibility: extends the same command model with MCP-specific subcommands.
- `src/superhaojun/agents/commands.py`
  Responsibility: extends the same command model with multi-agent control commands.
- `src/superhaojun/main.py`
  Responsibility: intercepts slash-prefixed input before it reaches the agent loop and dispatches to the command registry.
- `tests/test_commands.py`
  Responsibility: verifies registry behavior and representative built-in command behavior.

## Current Design

- Commands are resolved before the agent loop runs. The REPL treats any trimmed input starting with `/` as a command line.
- Parsing is intentionally shallow:
  - first token after `/` is the command name
  - remaining text is passed through as raw `args`
- `CommandContext` starts with only `agent` and `should_exit`, then callers attach extra capabilities dynamically such as `command_registry`, `session_manager`, `memory_store`, `mcp_manager`, or `model_registry`.
- Command behavior is deliberately local and synchronous from the operator's perspective:
  - mutate local agent state
  - return a short text response
  - optionally mark `should_exit`
- The WebUI command path reuses the same registry and context wiring, then returns results as `command_response` events so the frontend can surface them in chat.

## Open Questions

- `CommandContext` currently relies on ad hoc attributes attached by the caller. If command surface area keeps growing, the context contract may need to become explicit instead of remaining a dynamic bag of references.

## Verification

- Run `uv run pytest tests/test_commands.py -v`.
- Manually verify in the CLI that:
  - `/help` lists the current command set
  - unknown commands still offer completion hints
  - `/quit` and `/exit` still end the REPL
- If WebUI command handling changes, also verify `/model` and `/mcp list` through the browser chat surface.

## Follow-ups

- If command count grows much further, split built-in commands by responsibility instead of expanding `builtins.py` indefinitely.
