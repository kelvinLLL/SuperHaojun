# Feature Specs

This directory holds one file per active feature boundary.

## Naming

- Prefer short kebab-case names: `agent-loop.md`, `hooks-runtime.md`, `webui-chat.md`.
- Name the spec after the feature boundary, not a temporary task or bug ticket.

## When To Create

Create a new feature spec when:

- the work introduces a new user-facing or system-facing capability
- the work changes the boundary or structure of an existing subsystem
- the work needs durable feature-local context that should live near future implementation

## When To Update

Update an existing feature spec when:

- the feature already has a spec file
- the work changes its scope, file ownership, flow, or design decisions
- implementation reveals that the old spec no longer matches reality

## Authoring Rules

- Update the spec before writing code.
- Keep it concise and concrete.
- Record the current system, not aspirational architecture.
- Link to supporting material in `docs/` when needed, but keep the active contract in the feature spec.

## Current Set

The repo currently has active feature specs for:

- `agent-loop`
- `runtime-assembly`
- `conversation-core`
- `tool-orchestration`
- `turn-runtime`
- `model-config`
- `tool-system`
- `command-system`
- `prompt-context`
- `context-compaction`
- `session-persistence`
- `memory-store`
- `memory-entry`
- `hooks-runtime`
- `mcp-runtime`
- `mcp-approval`
- `lsp-feedback`
- `multi-agent`
- `skills-plugin-runtime`
- `webui-chat`
