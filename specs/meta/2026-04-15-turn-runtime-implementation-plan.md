# Turn Runtime Implementation Plan

**Goal:** Make the current turn state explicit and inspectable without changing the existing event stream or turn loop behavior.

**Approach:** Add a lightweight `TurnRuntimeState` module and let `Agent` update it as each LLM turn progresses. Expose that snapshot through WebUI init and a dedicated runtime endpoint so the harness shows raw internal turn state instead of only derived counters.

## Steps

1. Add failing tests for explicit turn runtime state and WebUI-facing serialization.
2. Implement `src/superhaojun/turn_runtime.py`.
3. Rewire `Agent` to update `turn_runtime` during streaming and tool transitions.
4. Expose the runtime snapshot from `webui/server.py`.
5. Run focused verification and update `specs/features/turn-runtime.md`.
