# MCP Approval Implementation Plan

## Scope

- Implement the first approval-gated MCP slice described in `specs/features/mcp-approval.md`.
- Keep the change small but end-to-end: config -> manager -> runtime -> command/WebUI visibility.

## Steps

1. Add failing tests for approval defaults, startup gating, `/mcp approve|deny`, and shared-runtime exposure.
2. Introduce explicit approval state in MCP config and manager state.
3. Block `start_all()` and `enable()` when approval is not granted.
4. Add explicit manager actions for approve and deny.
5. Surface approval through `get_status()`, `/mcp list`, and WebUI MCP APIs.
6. Attach `mcp_manager` to the shared runtime and register `/mcp` in built-in commands.
7. Run focused MCP and runtime verification, then update the feature doc to match the shipped design.
