# Turn Runtime Phase 2 Plan

## Scope

- Implement the second `turn-runtime` slice focused on explainable queue and counter state.
- Keep interrupt wiring out of this round and focus on state users can inspect immediately.

## Steps

1. Add failing tests for explicit tool queue status, token counters, and compaction metadata in runtime state.
2. Extend `TurnRuntimeState` with queue, token, and compaction fields plus update helpers.
3. Wire `Agent` and `ToolOrchestrator` to update runtime state during tool execution.
4. Source WebUI token usage from the shared runtime snapshot instead of ad hoc estimation.
5. Run focused runtime, tool, and compaction verification.
6. Update `specs/features/turn-runtime.md` so it reflects the shipped boundary.
