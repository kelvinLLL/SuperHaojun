# Runtime Assembly Tail Plan

Date: 2026-04-16
Feature: `runtime-assembly`

## Goal

Close the remaining runtime-assembly drift without reopening the larger architecture:

- launch TUI through shared runtime construction and lifecycle
- make `transport/` explicitly experimental so docs and code do not overstate its current role

## Planned Changes

1. Add a dedicated TUI launcher that uses `build_runtime()`.
2. Route TUI startup and shutdown through `AppRuntime.startup()` / `shutdown()`.
3. Keep `TUIApp` focused on UI behavior, not runtime construction.
4. Mark `transport/` as experimental in package surface/docs so it is no longer implied to be a first-class runtime boundary.
5. Update README and `runtime-assembly` spec to reflect the final entrypoint story.

## Verification

- `uv run pytest tests/test_runtime.py tests/test_tui.py tests/test_transport.py -v`
