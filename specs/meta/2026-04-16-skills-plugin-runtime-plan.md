# Skills Plugin Runtime Plan

Date: 2026-04-16
Feature: `skills-plugin-runtime`

## Goal

Implement a thin, repo-local extension runtime that makes reusable local workflow assets visible and controllable without building a heavyweight plugin system.

## Planned Changes

1. Add `ExtensionRuntime` for repo-local discovery and enable/disable overrides.
2. Feed loaded prompt-capable extensions into prompt assembly through the existing project-instructions section boundary.
3. Inject the extension runtime through shared runtime assembly and command context.
4. Add `/extensions` as the first shared visibility/control surface.
5. Expose extension metadata through WebUI/runtime state for explainability.

## Verification

- `uv run pytest tests/test_extensions.py tests/test_prompt.py tests/test_commands.py tests/test_runtime.py -v`
