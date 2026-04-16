---
title: Runtime Assembly
status: active
owner: Haojun
last_updated: 2026-04-16
source_paths:
  - src/superhaojun/runtime.py
  - src/superhaojun/extensions/runtime.py
  - src/superhaojun/main.py
  - src/superhaojun/webui/launcher.py
  - src/superhaojun/tui/launcher.py
  - src/superhaojun/tui/app.py
  - src/superhaojun/transport/__init__.py
  - src/superhaojun/webui/server.py
  - src/superhaojun/commands/base.py
  - src/superhaojun/commands/builtins.py
---

# Runtime Assembly

## Goal

- Define how shared runtime dependencies are constructed and injected across CLI, WebUI, and TUI entrypoints.
- Stop entrypoint drift so the same agent, command, session, memory, and permission semantics are available regardless of frontend.

## Scope

- In scope:
  - entrypoint-side construction of `Agent`, `MessageBus`, registries, prompt builder, memory store, session manager, and hook runner
  - command context wiring across app surfaces
  - shared runtime state that should be visible to users and UI consumers
  - design decisions about whether incomplete entrypoints stay first-class or become explicitly experimental
- Out of scope:
  - agent loop internals
  - tool implementation logic
  - frontend rendering details
  - transport protocol redesign

## File Structure

- `src/superhaojun/runtime.py`
  Responsibility: owns shared construction of the core agent runtime and exposes a single command-context builder used across entrypoints.
- `src/superhaojun/main.py`
  Responsibility: uses the shared runtime builder for the CLI path, registers terminal render handlers, and executes slash commands through the shared command-context contract.
- `src/superhaojun/webui/launcher.py`
  Responsibility: uses the shared runtime builder for the WebUI path and passes the full shared dependency set into the FastAPI app.
- `src/superhaojun/webui/server.py`
  Responsibility: adapts shared runtime objects for WebSocket and REST consumers, and builds command context through the shared helper instead of ad hoc attribute wiring.
- `src/superhaojun/tui/app.py`
  Responsibility: runs the richer terminal UI and now accepts a shared command context when one is provided, while falling back to the shared command-context helper.
- `src/superhaojun/tui/launcher.py`
  Responsibility: launches TUI through the shared runtime builder and shared runtime lifecycle instead of ad hoc assembly.
- `src/superhaojun/transport/__init__.py`
  Responsibility: makes the current transport package status explicit so the repo does not imply it is already a first-class runtime surface.
- `src/superhaojun/commands/base.py`
  Responsibility: defines the shared command contract and the shape of runtime context passed into commands.
- `src/superhaojun/commands/builtins.py`
  Responsibility: reveals which runtime dependencies commands actually need, including model registry, session manager, and memory store.

## Current Design

- The repo now has a shared runtime assembly boundary in `src/superhaojun/runtime.py`.
- `build_runtime()` constructs one consistent dependency set for:
  - `Agent`
  - `MessageBus`
  - tool registry
  - command registry
  - model registry
  - session manager
  - memory store
  - extension runtime
  - prompt builder
  - hook registry and optional hook runner
  - MCP manager
- `AppRuntime.build_command_context()` is now the canonical place to inject command dependencies, and the same dependency set is available to CLI, WebUI, and TUI commands.
- The CLI path now uses the shared runtime builder instead of assembling the runtime inline.
- The WebUI launcher now uses the shared runtime builder and passes `session_manager`, `memory_store`, `mcp_manager`, and `extension_runtime` alongside the other shared registries, removing another real command-surface drift.
- `AppRuntime` now also owns startup and shutdown of optional runtime services, so entrypoints do not each need to rediscover how MCP lifecycle should start or stop.
- TUI is not fully launched through `AppRuntime` yet, but it now uses the shared command-context helper and supports an explicitly provided shared `CommandContext`, which removes the earlier command signature drift.
- TUI now has a dedicated launcher that reuses `build_runtime()`, `AppRuntime.startup()`, and `AppRuntime.shutdown()`, so terminal UI startup semantics now match CLI and WebUI.
- `transport/` remains a useful local helper package, but it is not a first-class runtime assembly boundary yet. The package now marks that status explicitly as experimental until a real cross-boundary runtime consumes it.
- This feature now owns construction and dependency injection, while frontend-specific rendering still stays outside the shared runtime layer.
- Explainability is part of the runtime boundary, not a WebUI-only concern. Shared runtime state should be structured so every frontend can show what the harness is doing instead of reconstructing hidden state from side effects.

## Open Questions

- Whether TUI should eventually share more launcher helpers with CLI after the dedicated TUI launcher exists.
- Whether `transport/` should be promoted into this boundary later, once a real cross-boundary runtime uses it.

## Verification

- Run `uv run pytest tests/test_commands.py -v`.
- Run `uv run pytest tests/test_tui.py -v`.
- Run `uv run pytest tests/test_transport.py -v`.
- Run `uv run pytest tests/test_agent.py -v`.
- When editing this feature later, confirm that:
  - the same command works with the same dependencies in CLI, WebUI, and TUI
  - runtime-only state does not disappear just because a different frontend is active
  - entrypoint wiring changes do not silently remove session or memory features from one surface
  - `transport/` does not get described as first-class runtime plumbing before a real entrypoint uses it

## Follow-ups

- Revisit whether CLI and TUI should share more terminal-launcher helpers now that both are built on the same runtime boundary.
- Revisit `transport/` only when a real cross-boundary runtime is ready to consume it.
