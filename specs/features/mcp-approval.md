---
title: MCP Approval
status: active
owner: Haojun
last_updated: 2026-04-16
source_paths:
  - src/superhaojun/mcp/config.py
  - src/superhaojun/mcp/manager.py
  - src/superhaojun/webui/server.py
  - src/superhaojun/mcp/commands.py
  - src/superhaojun/runtime.py
  - src/superhaojun/commands/__init__.py
  - tests/test_mcp.py
  - tests/test_runtime.py
---

# MCP Approval

## Goal

- Add an explicit trust and approval boundary for MCP servers, especially project-scoped servers that introduce external capabilities into the harness.
- Make MCP connection decisions visible and controllable instead of treating `enabled` as the whole trust model.

## Scope

- In scope:
  - approval state for MCP servers
  - trust semantics for project versus user scope
  - UI and command visibility for pending, approved, denied, disabled, and error states
  - approval-driven lifecycle gating before server startup
- Out of scope:
  - MCP protocol implementation
  - remote approval sync
  - marketplace-style MCP discovery

## File Structure

- `src/superhaojun/mcp/config.py`
  Responsibility: defines persistent MCP configuration, which is the likely home of future approval metadata or approval-policy references.
- `src/superhaojun/mcp/manager.py`
  Responsibility: owns MCP lifecycle and therefore is the runtime gate where approval must be enforced before startup.
- `src/superhaojun/webui/server.py`
  Responsibility: exposes MCP state to browser consumers and is the current API surface for status and lifecycle actions.
- `src/superhaojun/mcp/commands.py`
  Responsibility: provides operator-facing MCP control from the CLI path.
- `src/superhaojun/runtime.py`
  Responsibility: assembles the shared runtime and must attach the MCP manager where CLI and WebUI can both see the same approval-gated state.
- `src/superhaojun/commands/__init__.py`
  Responsibility: registers the built-in slash-command surface and should expose `/mcp` when MCP runtime support exists in the shared command context.
- `tests/test_mcp.py`
  Responsibility: protects current MCP lifecycle behavior and will need to cover approval gating once added.
- `tests/test_runtime.py`
  Responsibility: verifies that the shared runtime includes the MCP manager in the same dependency surface exposed to commands and browser consumers.

## Current Design

- MCP approval now exists as a distinct state separate from both config scope and runtime status.
- `MCPServerConfig` supports explicit approval metadata, and approval defaults are scope-aware:
  - user-scope servers default to `approved`
  - project-scope servers default to `pending`
  - config can explicitly mark a server `approved` or `denied`
- `MCPManager` stores approval on `MCPServerState` and gates lifecycle from that state:
  - `start_all()` skips servers whose approval is not granted
  - `enable()` and `reconnect()` refuse to start pending or denied servers
  - `approve()` and `deny()` are explicit runtime actions
  - `deny()` stops a running server before leaving it visible in denied state
- `enabled` now stays focused on availability intent instead of trust semantics.
- Approval is visible in both operator surfaces:
  - `/mcp list` now reports approval alongside status, transport, scope, and error text
  - WebUI MCP action endpoints accept `approve` and `deny`, and status payloads now include approval
- This feature also closes the runtime gap that previously hid MCP behind dead wiring:
  - the shared runtime now exposes `mcp_manager`
  - built-in commands now include `/mcp`
  - CLI and WebUI both operate on the same approval-gated manager state

## Open Questions

- Whether runtime approval changes should eventually persist back into `.haojun/mcp.json` or remain session-local until an explicit config-writing flow exists.
- Whether future approval should distinguish "approve once" from "approve for this repo".

## Verification

- Run `uv run pytest tests/test_mcp.py -v`.
- Run `uv run pytest tests/test_runtime.py -v`.
- When changing this feature later, confirm that:
  - project scope still overrides user scope where intended
  - unapproved servers do not auto-start or manually enable
  - approval state is visible in CLI and WebUI surfaces
  - approved servers still register tools normally after startup

## Follow-ups

- Keep `mcp-runtime` focused on lifecycle and protocol integration, and let this feature own trust semantics.
- Add an explicit approval update path that keeps `MCPServerConfig` synchronized with runtime approval changes so the manager has a clear state transition boundary and future config persistence can reuse the same data.
- Revisit whether approval should become part of a broader external-capability trust model once other plugin-like systems exist.
