# Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a shared runtime assembly boundary and extract the conversation model out of `agent.py` without regressing current CLI, WebUI, session, or compaction behavior.

**Architecture:** Add a small shared runtime module that constructs the common agent dependencies once and exposes a single command-context builder for all entrypoints. In parallel, extract `ChatMessage` and a lightweight `ConversationState` into a dedicated conversation module, then point agent, session, compaction, and WebUI serialization at that shared boundary while keeping `Agent.messages` compatible for current callers.

**Tech Stack:** Python 3.12, dataclasses, FastAPI, prompt_toolkit, pytest

---

## File Structure

- Create: `src/superhaojun/runtime.py`
  Purpose: shared runtime assembly dataclass + builder + command-context helper used by CLI and WebUI first, with TUI-compatible hooks.
- Create: `src/superhaojun/conversation.py`
  Purpose: shared transcript model (`ChatMessage`) and lightweight `ConversationState`.
- Modify: `src/superhaojun/agent.py`
  Purpose: consume conversation boundary instead of defining transcript types inline; remain backward compatible through `messages`.
- Modify: `src/superhaojun/main.py`
  Purpose: replace ad hoc CLI assembly with the shared runtime builder.
- Modify: `src/superhaojun/webui/launcher.py`
  Purpose: replace ad hoc WebUI assembly with the shared runtime builder and pass the full dependency set.
- Modify: `src/superhaojun/webui/server.py`
  Purpose: serialize conversation through the shared model and use a single command-context builder.
- Modify: `src/superhaojun/tui/app.py`
  Purpose: fix command invocation order and accept a shared command context when available.
- Modify: `src/superhaojun/session/manager.py`
  Purpose: import transcript types from `conversation.py` and centralize message serialization.
- Modify: `src/superhaojun/compact/compactor.py`
  Purpose: import transcript types from `conversation.py`.
- Modify: `src/superhaojun/compact/session_compact.py`
  Purpose: import transcript types from `conversation.py`.
- Modify: `tests/test_commands.py`
  Purpose: cover consistent command-context dependencies.
- Modify: `tests/test_agent.py`
  Purpose: cover agent compatibility with extracted conversation state.
- Modify: `tests/test_session.py`
  Purpose: cover session round-trip through shared conversation serialization.
- Modify: `tests/test_compact.py`
  Purpose: cover compactor compatibility with extracted conversation types.
- Create: `tests/test_runtime.py`
  Purpose: cover shared runtime builder and consistent command-context wiring.

### Task 1: Shared Runtime Builder

**Files:**
- Create: `src/superhaojun/runtime.py`
- Modify: `src/superhaojun/main.py`
- Modify: `src/superhaojun/webui/launcher.py`
- Modify: `src/superhaojun/webui/server.py`
- Modify: `src/superhaojun/tui/app.py`
- Test: `tests/test_runtime.py`

- [ ] **Step 1: Write the failing runtime-assembly tests**

```python
def test_build_runtime_includes_command_dependencies(tmp_path: Path) -> None:
    runtime = build_runtime(working_dir=tmp_path)
    ctx = runtime.build_command_context()
    assert ctx.command_registry is runtime.command_registry
    assert ctx.model_registry is runtime.model_registry
    assert ctx.session_manager is runtime.session_manager
    assert ctx.memory_store is runtime.memory_store
```

- [ ] **Step 2: Run the runtime tests to verify they fail**

Run: `uv run pytest tests/test_runtime.py -v`
Expected: FAIL because `build_runtime` and `AppRuntime` do not exist yet.

- [ ] **Step 3: Implement the minimal shared runtime module**

```python
@dataclass
class AppRuntime:
    ...

    def build_command_context(self) -> CommandContext:
        ...


def build_runtime(*, working_dir: str, model_registry: ModelRegistry | None = None) -> AppRuntime:
    ...
```

- [ ] **Step 4: Route CLI and WebUI through the shared builder**

Run: `uv run pytest tests/test_runtime.py tests/test_commands.py -v`
Expected: PASS for the new runtime tests and no regressions in command behavior.

- [ ] **Step 5: Bring TUI onto the same command-context contract**

Run: `uv run pytest tests/test_tui.py tests/test_runtime.py -v`
Expected: PASS with corrected command execution argument order and context handling.

### Task 2: Extract Conversation Core

**Files:**
- Create: `src/superhaojun/conversation.py`
- Modify: `src/superhaojun/agent.py`
- Modify: `src/superhaojun/session/manager.py`
- Modify: `src/superhaojun/compact/compactor.py`
- Modify: `src/superhaojun/compact/session_compact.py`
- Modify: `src/superhaojun/webui/server.py`
- Test: `tests/test_agent.py`
- Test: `tests/test_session.py`
- Test: `tests/test_compact.py`

- [ ] **Step 1: Write the failing conversation-core tests**

```python
def test_agent_exposes_shared_conversation_state(agent: Agent) -> None:
    assert agent.conversation.messages is agent.messages


def test_session_roundtrip_preserves_reasoning_details(tmp_path: Path) -> None:
    ...
```

- [ ] **Step 2: Run the conversation tests to verify they fail**

Run: `uv run pytest tests/test_agent.py tests/test_session.py tests/test_compact.py -v`
Expected: FAIL because `conversation.py` does not exist and transcript serialization is still owned by `agent.py`.

- [ ] **Step 3: Implement the minimal conversation boundary**

```python
@dataclass
class ChatMessage:
    ...


@dataclass
class ConversationState:
    messages: list[ChatMessage] = field(default_factory=list)
```

- [ ] **Step 4: Rewire agent, session, compaction, and WebUI serialization**

Run: `uv run pytest tests/test_agent.py tests/test_session.py tests/test_compact.py -v`
Expected: PASS with no remaining imports of transcript types from `agent.py` in persistence or compaction modules.

- [ ] **Step 5: Preserve compatibility for current callers**

Run: `uv run pytest tests/test_commands.py tests/test_agent.py tests/test_session.py tests/test_compact.py -v`
Expected: PASS with `agent.messages` still working for commands and legacy callers.

### Task 3: Docs Sync and Focused Verification

**Files:**
- Modify: `specs/features/runtime-assembly.md`
- Modify: `specs/features/conversation-core.md`
- Modify: `specs/development-rules.md` (only if a reusable implementation rule emerges)

- [ ] **Step 1: Update feature specs to match the implemented boundaries**

Document the new shared runtime module, the extracted conversation module, and any deliberate compatibility shims.

- [ ] **Step 2: Run focused verification**

Run: `uv run pytest tests/test_runtime.py tests/test_commands.py tests/test_agent.py tests/test_session.py tests/test_compact.py tests/test_tui.py -v`
Expected: PASS for the touched runtime and conversation surfaces.

- [ ] **Step 3: Record any reusable rule if discovered**

If implementation reveals a cross-feature rule about runtime state visibility or shared dependency injection, promote it into `specs/development-rules.md`.
