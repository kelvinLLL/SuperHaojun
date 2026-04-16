# Memory Entry Implementation Plan

## Scope

- Implement the first bounded `memory-entry` slice.
- Replace flat full-memory prompt export with a structured entry surface built from `MEMORY.md` plus a small bounded topic expansion.
- Expose injected-memory metadata through shared runtime state.

## Steps

1. Add failing tests for bounded prompt-entry export, prompt-builder metadata plumbing, command refresh after memory mutation, and runtime visibility.
2. Introduce a structured memory-entry export in `MemoryStore` that uses the index plus bounded recent topic snippets.
3. Keep `to_prompt_text()` backward-compatible by delegating to the new bounded export.
4. Teach `SystemPromptBuilder` to carry both memory text and memory-entry metadata.
5. Refresh prompt memory entry from shared runtime wiring and `/memory` mutations.
6. Record injected-memory metadata in `TurnRuntimeState` so the active turn shows which durable memory influenced it.
7. Run focused verification and update `specs/features/memory-entry.md` to reflect the shipped design.
