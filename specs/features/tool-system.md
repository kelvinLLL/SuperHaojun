---
title: Tool System
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/tools/base.py
  - src/superhaojun/tools/registry.py
  - src/superhaojun/tools/__init__.py
  - src/superhaojun/tools
  - tests/test_tools.py
  - tests/test_core_tools.py
---

# Tool System

## Goal

- Provide the agent with a small, composable set of callable tools.
- Keep tool declaration simple enough that new tools can be added without changing the agent loop.

## Scope

- In scope:
  - the `Tool` ABC
  - tool metadata and OpenAI schema conversion
  - registry lookup and registration
  - built-in file, shell, and search tools
- Out of scope:
  - tool orchestration order inside the agent loop
  - permission decision policy
  - MCP-provided tool lifecycle

## File Structure

- `src/superhaojun/tools/base.py`
  Responsibility: defines the abstract tool contract and the default metadata used by orchestration and permission logic.
- `src/superhaojun/tools/registry.py`
  Responsibility: stores named tools and converts the full registry into OpenAI function-calling definitions.
- `src/superhaojun/tools/*.py`
  Responsibility: implement the built-in tool behaviors such as file read/write/edit, bash, glob, grep, and list-dir.
- `tests/test_tools.py`
  Responsibility: verifies the base tool contract, schema conversion, registry behavior, and representative tool behavior.
- `tests/test_core_tools.py`
  Responsibility: regression coverage for the built-in tool set as a whole.

## Current Design

- Every tool implements four required members:
  - `name`
  - `description`
  - `parameters`
  - `execute(**kwargs)`
- Two optional properties shape runtime behavior without coupling tools to the agent loop:
  - `is_concurrent_safe`
  - `risk_level`
- `to_openai_tool()` is the only serialization step needed for model tool calling. The tool system does not add a second schema layer on top of JSON Schema.
- `ToolRegistry` is intentionally small:
  - register by tool name
  - overwrite on duplicate registration
  - lookup by name
  - batch export to OpenAI tool definitions
- Built-in tools are registered centrally through `register_builtin_tools()` and then shared by the CLI agent, WebUI server, and multi-agent components.
- The agent loop treats tools as declarative capabilities. It reads `is_concurrent_safe` to separate concurrent and sequential execution, and it reads `risk_level` to route permission checks.

## Open Questions

- The tool contract relies on JSON Schema and tool code discipline, but there is no dedicated runtime argument validation layer before `execute()` runs. If stricter validation is needed later, it should live at this boundary rather than inside each tool.

## Verification

- Run `uv run pytest tests/test_tools.py -v`.
- Run `uv run pytest tests/test_core_tools.py -v`.
- When changing tool metadata, confirm that:
  - the registry still exports valid OpenAI tool definitions
  - the CLI `/tools` output still reflects the current tool set
  - the agent loop still classifies tool concurrency and risk correctly

## Follow-ups

- Keep execution policy and queue state in `tool-orchestration` instead of letting this feature absorb runtime scheduling concerns.
- If MCP and built-in tools begin to diverge in metadata needs, introduce a shared protocol layer without breaking the simple built-in tool contract.
