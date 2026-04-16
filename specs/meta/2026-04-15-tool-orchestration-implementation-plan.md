# Tool Orchestration Implementation Plan

**Goal:** Extract tool execution policy and permission or hook wrapping out of `agent.py` into a dedicated orchestrator without changing visible agent behavior.

**Approach:** Add a small `ToolOrchestrator` module that owns concurrent versus sequential batching and per-tool execution. Keep `Agent` responsible for turn control and transcript append behavior so this stays a narrow refactor instead of a full runtime rewrite.

## Steps

1. Add failing tests for a dedicated orchestrator boundary.
2. Implement `src/superhaojun/tool_orchestration.py` with:
   - `ToolCallInfo`
   - `ToolExecutionResult`
   - `ToolOrchestrator`
3. Rewire `Agent` to use the orchestrator instead of owning tool execution methods directly.
4. Run focused verification for `tests/test_agent.py` and the new orchestration tests.
5. Update `specs/features/tool-orchestration.md` so it reflects the final code boundary.
