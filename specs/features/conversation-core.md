---
title: Conversation Core
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/conversation.py
  - src/superhaojun/agent.py
  - src/superhaojun/session/manager.py
  - src/superhaojun/compact/compactor.py
  - src/superhaojun/compact/session_compact.py
  - src/superhaojun/webui/server.py
  - tests/test_agent.py
  - tests/test_session.py
  - tests/test_compact.py
---

# Conversation Core

## Goal

- Define the durable conversation model that sits underneath the agent loop, session persistence, and context compaction.
- Separate transcript ownership from runtime orchestration so message history can evolve without forcing unrelated code to depend on `Agent`.

## Scope

- In scope:
  - the in-memory transcript model currently represented by `Agent.messages`
  - the `ChatMessage` data shape and its consumers
  - persistence and compaction boundaries that read and write conversation history
  - surface-level serialization of transcript state for WebUI and tests
- Out of scope:
  - message-bus protocol types in `messages.py`
  - tool implementation details
  - frontend display formatting
  - model provider configuration

## File Structure

- `src/superhaojun/conversation.py`
  Responsibility: owns the shared transcript model (`ChatMessage`) and lightweight in-memory transcript container (`ConversationState`).
- `src/superhaojun/agent.py`
  Responsibility: owns runtime orchestration and consumes the shared conversation boundary, while exposing `messages` as a backward-compatible alias.
- `src/superhaojun/session/manager.py`
  Responsibility: persists and reloads transcript entries through the shared conversation model, including transcript-only fields such as `reasoning_details`.
- `src/superhaojun/compact/compactor.py`
  Responsibility: estimates transcript size, summarizes older messages, and emits compacted replacement messages against the shared conversation model.
- `src/superhaojun/compact/session_compact.py`
  Responsibility: derives session-level summaries from the same transcript shape used by the agent loop.
- `src/superhaojun/webui/server.py`
  Responsibility: serializes current transcript state for WebUI clients from the shared conversation model, including reasoning details.
- `tests/test_agent.py`, `tests/test_session.py`, `tests/test_compact.py`
  Responsibility: encode the current conversation model contract across runtime, persistence, and compaction behaviors.

## Current Design

- The repo now has a dedicated conversation boundary in `src/superhaojun/conversation.py`.
- `ChatMessage` is no longer defined inside `agent.py`; it lives in the shared conversation module alongside `ConversationState`.
- `Agent` now owns `conversation: ConversationState` and exposes `messages` as a backward-compatible alias to `conversation.messages`.
- Session persistence and compaction no longer import transcript types from `agent.py`; they import from the shared conversation module instead.
- Transcript serialization is now more consistent:
  - session save and load use `ChatMessage.to_dict()` and `ChatMessage.from_dict()`
  - `reasoning_details` now round-trips through session persistence
  - WebUI transcript serialization includes `reasoning_details`
- This removes the strongest reverse dependency pressure on `agent.py`. Runtime orchestration still reads and writes the transcript, but it no longer defines the durable transcript type.
- This feature also owns explainability at the transcript layer. The system should preserve raw, inspectable conversation structure and state transitions instead of collapsing them into opaque summaries too early.

## Open Questions

- Whether the extracted boundary should center on a single `ConversationState` object or on a smaller `Transcript` model plus separate runtime state.
- Whether reasoning details should remain a transcript concern or move into a richer assistant-message payload type when the conversation model is extracted.

## Verification

- Run `uv run pytest tests/test_agent.py -v`.
- Run `uv run pytest tests/test_session.py -v`.
- Run `uv run pytest tests/test_compact.py -v`.
- When changing this feature later, confirm that:
  - session save/load still round-trips all supported transcript fields
  - compaction still accepts the shared conversation model without importing orchestration-only code
  - WebUI transcript serialization still reflects the real conversation state after extraction

## Follow-ups

- Align this feature with `agent-loop` once transcript ownership moves out of `agent.py`.
- If a richer conversation state object is introduced, document which parts are durable transcript, which parts are runtime-only, and which parts must be surfaced to users for explainability.
