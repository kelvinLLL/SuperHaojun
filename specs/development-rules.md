# Development Rules

These rules apply to all active feature work in `superhaojun`.

## Core Rules

- Start feature work in `specs/`, not in `docs/`.
- No code before doc when a change affects a feature boundary, flow, or structure.
- Keep feature-local decisions in that feature's spec file.
- Keep reusable cross-feature rules in this file.
- Update the spec in the same work when code changes the active design.

## Feature Spec Requirements

Every active feature spec must include:

- header metadata
- `Goal`
- `Scope`
- `File Structure`
- `Current Design`

`File Structure` must explain responsibilities, not just list filenames.

## Docs Boundary

- `specs/` is for active implementation contracts.
- `docs/` is for explanatory and historical material.
- If a `docs/` note contains implementation-critical context, summarize the needed part in the relevant feature spec instead of treating the note as the live contract.

## Promotion Rule

Promote a lesson into this file when it is likely to matter in another feature and would improve future implementation choices if remembered.

## Explainability First

- Prefer exposing runtime state over hiding it behind summaries when both are possible.
- Treat agent phases, queues, pending decisions, and key counters as product-visible state, not debug-only internals.
- Add summaries only as an extra layer. They must not replace the raw event or state view needed to understand what the harness is doing.
