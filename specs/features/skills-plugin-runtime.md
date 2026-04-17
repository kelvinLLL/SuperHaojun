---
title: Skills Plugin Runtime
status: active
owner: Haojun
last_updated: 2026-04-17
source_paths:
  - src/superhaojun/extensions/runtime.py
  - src/superhaojun/commands/builtins.py
  - src/superhaojun/prompt/sections/project_instructions.py
  - src/superhaojun/prompt/builder.py
  - src/superhaojun/prompt/context.py
  - src/superhaojun/runtime.py
  - src/superhaojun/hooks/config.py
  - src/superhaojun/webui/server.py
  - specs
---

# Skills Plugin Runtime

## Goal

- Define a repo-local extension mechanism for loading reusable skills, workflow rules, and plugin-like capabilities without hardcoding them into the core runtime.
- Give future SDD rules, repo methods, and optional runtime enhancements a clear load boundary and visible lifecycle.

## Scope

- In scope:
  - local skills or plugin metadata loading
  - source visibility and enable or disable boundaries
  - interaction with prompt assembly, hooks, and runtime registration
  - repo-local extension strategy only
- Out of scope:
  - remote marketplaces
  - cross-machine sync
  - third-party billing or distribution concerns

## File Structure

- `src/superhaojun/extensions/runtime.py`
  Responsibility: discovers repo-local extension sources, applies enable/disable overrides, and exposes prompt/runtime views of loaded extensions.
- `src/superhaojun/commands/builtins.py`
  Responsibility: exposes a shared slash-command surface for listing and toggling repo-local extensions.
- `src/superhaojun/prompt/sections/project_instructions.py`
  Responsibility: renders prompt-facing repo-local extension content, reusing the existing instruction boundary instead of adding more hardcoded prompt text.
- `src/superhaojun/prompt/builder.py`
  Responsibility: owns the prompt-side attachment point for loaded repo-local extensions and keeps prompt cache invalidation aligned with extension changes.
- `src/superhaojun/prompt/context.py`
  Responsibility: carries loaded extension entries into prompt sections without forcing those sections to rediscover files on their own.
- `src/superhaojun/runtime.py`
  Responsibility: assembles the shared repo-local extension runtime once and injects it into command, prompt, and UI surfaces.
- `src/superhaojun/hooks/config.py`
  Responsibility: remains one of the extension source types surfaced by the unified runtime, instead of staying a separate invisible mechanism.
- `src/superhaojun/webui/server.py`
  Responsibility: exposes loaded repo-local extensions to browser consumers and keeps extension state visible in runtime snapshots.
- `specs/`
  Responsibility: already holds durable workflow rules and feature contracts, which makes this repo a strong candidate for a repo-local extension model instead of more hardcoded prompt text.

## Current Design

- The repo already has several extension-like ideas, but they are not unified:
  - project instruction discovery
  - hooks
  - `specs/development-rules.md`
  - MCP-provided external tools
- The first implementation boundary for this feature is a local `ExtensionRuntime` that discovers a small set of repo-local extension sources and makes them inspectable:
  - instruction files (`SUPERHAOJUN.md`, `AGENT.md`, including `.haojun/`)
  - `specs/development-rules.md` as workflow-rules input
  - `.haojun/hooks.json` as a runtime-visible extension source
- `ExtensionRuntime` owns:
  - source discovery
  - stable ids
  - enable/disable overrides via repo-local config
  - prompt-facing text for prompt-capable extensions
  - runtime-facing metadata for explainable UI and slash-command inspection
- `ProjectInstructionsSection` becomes the prompt rendering boundary for these repo-local extensions instead of rediscovering files ad hoc when runtime metadata is available.
- `runtime.py` loads one shared extension runtime and injects it into:
  - the prompt builder
  - slash command context
  - WebUI extras/runtime snapshots
- The first user-facing control surface is `/extensions`, which now shows what is loaded, where it came from, and whether it is enabled. Enabling or disabling an extension invalidates prompt caches immediately.
- Browser consumers can inspect the same extension state through WebUI runtime snapshots and `/api/extensions`, so extension loading is not hidden behind CLI-only tooling.
- WebUI extension governance is now part of the feature boundary:
  - browser users should be able to enable or disable repo-local extensions through explicit buttons instead of only slash commands
  - the backend should expose extension-management endpoints that reuse the same `ExtensionRuntime.enable()` / `disable()` behavior and prompt-cache invalidation path as the slash command
  - browser state should refresh from the authoritative runtime after each toggle instead of inventing a separate extension cache
- This governance surface now shares the browser with built-in tool governance:
  - tools and repo-local extensions are exposed as separate controls, but both are governed from the same settings surface
  - disabling an extension removes its prompt contribution while preserving inspectable metadata
  - disabling a tool removes it from subsequent tool advertisement without unregistering the underlying implementation object
- Real-world verification for this feature now includes button-driven behavior, not only CLI parity:
  - extension toggles are covered by WebUI endpoint tests
  - browser approval flows can now be tested against a live model profile that emits real tool calls before write execution
- This feature deliberately stays local and inspectable. It does not add marketplace, remote sync, or arbitrary code execution.

## Open Questions

- Whether later versions should grow from this registry into richer skill manifests, or keep the runtime intentionally thin and repo-local.
- Whether future extensions should contribute only prompt and runtime metadata, or eventually register additional commands or runtime components.

## Verification

- Run `uv run pytest tests/test_extensions.py -v`.
- Run `uv run pytest tests/test_prompt.py -v`.
- Run `uv run pytest tests/test_commands.py -v`.
- Run `uv run pytest tests/test_runtime.py -v`.
- When editing this feature later, verify at minimum that:
  - loaded extension sources are visible to users
  - disabled extensions do not silently affect prompt or runtime behavior
  - prompt cache invalidation happens when extension state changes
  - slash-command and button-driven toggles keep the same runtime result
  - tool-governance toggles do not silently re-advertise disabled tools
  - repo-local extensions remain local and do not require remote infrastructure

## Follow-ups

- Revisit whether this local runtime should later subsume more spec-driven assets once real usage patterns settle.
