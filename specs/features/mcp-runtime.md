---
title: MCP Runtime
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/mcp/config.py
  - src/superhaojun/mcp/manager.py
  - src/superhaojun/mcp/client.py
  - src/superhaojun/mcp/adapter.py
  - src/superhaojun/mcp/commands.py
  - src/superhaojun/runtime.py
  - src/superhaojun/commands/__init__.py
  - src/superhaojun/webui/server.py
  - tests/test_mcp.py
  - tests/test_runtime.py
---

# MCP Runtime

## Goal

- Load MCP server definitions from local and user scopes.
- Manage MCP server lifecycle at runtime and expose discovered tools through the normal tool registry.

## Scope

- In scope:
  - config loading and scope merge
  - runtime status tracking
  - start/stop/enable/disable/reconnect behavior
  - MCP tool registration through adapters
  - CLI `/mcp` control surface
  - WebUI status endpoints
- Out of scope:
  - the agent loop's generic tool orchestration
  - MCP server implementation code
  - long-lived background config reloads

## File Structure

- `src/superhaojun/mcp/config.py`
  Responsibility: defines `MCPServerConfig`, status enums, and user-plus-project config merge behavior.
- `src/superhaojun/mcp/manager.py`
  Responsibility: owns per-server runtime state, lifecycle transitions, and tool registration or unregistration.
- `src/superhaojun/mcp/client.py`
  Responsibility: speaks the underlying MCP protocol to a single server process or endpoint.
- `src/superhaojun/mcp/adapter.py`
  Responsibility: wraps discovered MCP tools so they appear as normal `Tool` instances to the agent.
- `src/superhaojun/mcp/commands.py`
  Responsibility: exposes MCP management through `/mcp` subcommands.
- `src/superhaojun/runtime.py`
  Responsibility: wires MCP config loading and manager lifecycle into the shared runtime used by CLI and WebUI.
- `src/superhaojun/commands/__init__.py`
  Responsibility: registers `/mcp` into the normal built-in command surface instead of leaving MCP control as an unhooked capability.
- `src/superhaojun/webui/server.py`
  Responsibility: exposes MCP status and lifecycle actions over the WebUI API.
- `tests/test_mcp.py`
  Responsibility: verifies config loading, manager behavior, command output, and tool adapter expectations.
- `tests/test_runtime.py`
  Responsibility: verifies that shared runtime assembly exposes the MCP manager to command consumers.

## Current Design

- MCP config is loaded from two scopes:
  - user scope
  - project scope
- Server names are the merge key, and project scope wins when the same server appears in both places.
- `MCPManager` tracks one `MCPServerState` per server, including config, runtime status, approval state, connected client, discovered tools, and last error text.
- Lifecycle control is centralized in the manager:
  - `start_all()`
  - `stop_all()`
  - `enable()`
  - `disable()`
  - `reconnect()`
- On successful start, the manager asks the client for tool definitions and registers `MCPToolAdapter` instances into the main `ToolRegistry`.
- On stop or disable, the manager unregisters those adapted tool names using the `mcp__<server>__<tool>` naming scheme.
- Shared runtime assembly now loads MCP config, attaches the manager to `AppRuntime`, and starts or stops the manager with the entrypoint lifecycle.
- The `/mcp` command and `/api/mcp/*` endpoints are thin consumers over manager state rather than owning lifecycle rules themselves.

## Open Questions

- Config loading is additive, but runtime config reload semantics are still minimal. Changing an existing server definition after startup is not yet treated as a first-class update flow.

## Verification

- Run `uv run pytest tests/test_mcp.py -v`.
- Run `uv run pytest tests/test_runtime.py -v`.
- When editing runtime lifecycle behavior, confirm:
  - project scope still overrides user scope
  - adapted MCP tools are registered on start and removed on stop
  - `/mcp list` still reports status, approval, transport, scope, and error text
  - WebUI `/api/mcp/status` still reflects manager state

## Follow-ups

- Keep trust and approval semantics in `mcp-approval` instead of widening this feature from lifecycle management into policy management.
- If MCP usage grows, split protocol-client details from lifecycle management rather than letting `MCPManager` absorb protocol complexity.
