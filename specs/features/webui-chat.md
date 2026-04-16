---
title: WebUI Chat
status: active
owner: Haojun
last_updated: 2026-04-16
source_paths:
  - src/superhaojun/webui/server.py
  - src/superhaojun/webui/static/index.html
  - webui/src/App.tsx
  - webui/index.html
  - webui/public/favicon.svg
  - webui/src/hooks/useWebSocket.ts
  - webui/src/stores/index.ts
  - webui/src/components/chat/ChatView.tsx
  - webui/src/components/chat/ChatInput.tsx
  - webui/src/types/index.ts
---

# WebUI Chat

## Goal

- Provide a browser-based chat surface over the shared agent runtime.
- Mirror the CLI agent loop with real-time streaming, tool status, permission prompts, and control panels.

## Scope

- In scope:
  - FastAPI WebSocket and REST endpoints
  - browser WebSocket client behavior
  - chat state stores
  - chat rendering, input, and permission modal flow
  - model and command metadata fetches used by the UI
- Out of scope:
  - frontend build tooling
  - visual design system decisions beyond current component behavior
  - backend agent-loop implementation itself

## File Structure

- `src/superhaojun/webui/server.py`
  Responsibility: exposes the FastAPI app, forwards bus events to browser clients, handles incoming WebSocket messages, tracks the active browser agent task, and serves state-query REST endpoints.
- `src/superhaojun/webui/static/index.html`
  Responsibility: serves the built browser shell that FastAPI returns in production, including static asset references such as the favicon.
- `webui/index.html`
  Responsibility: defines the source HTML shell for the Vite app so browser metadata and static asset links survive frontend rebuilds.
- `webui/public/favicon.svg`
  Responsibility: provides the browser-visible favicon asset that is copied into the built static bundle and suppresses missing-icon 404 noise during real WebUI sessions.
- `webui/src/App.tsx`
  Responsibility: wires the chat view to the shared WebSocket hook and passes chat-level actions such as send, permission responses, and interrupt.
- `webui/src/hooks/useWebSocket.ts`
  Responsibility: owns the browser WebSocket connection, reconnection behavior, protocol handling, hydration of init snapshots, runtime/token synchronization, and outbound message helpers.
- `webui/src/stores/index.ts`
  Responsibility: stores chat state, tool-call state, permission prompts, panel data, models, diagnostics, and command metadata.
- `webui/src/components/chat/ChatView.tsx`
  Responsibility: renders the main chat timeline, empty state, streaming output, tool-call cards, permission modal, and chat-level controls such as interrupt.
- `webui/src/components/chat/ChatInput.tsx`
  Responsibility: collects user input, exposes slash-command autocomplete, and renders send/interrupt controls based on chat runtime state.
- `webui/src/types/index.ts`
  Responsibility: defines the browser-side protocol and store data types.

## Current Design

- The backend does not implement a separate browser-specific agent. It reuses the same `Agent` and `MessageBus` used elsewhere and forwards bus events to all connected WebSocket clients.
- The WebSocket protocol supports:
  - `user_message`
  - `permission_response`
  - `interrupt`
  - `ping` / `pong`
  - `runtime_state`
- Slash commands are intercepted server-side for browser clients in the same way the CLI intercepts them before reaching the agent loop.
- The frontend keeps a singleton WebSocket connection with simple reconnect logic and translates protocol messages into Zustand store updates.
- Chat rendering is state-driven:
  - explicit user messages are added optimistically on send
  - the initial `init.messages` payload hydrates the chat timeline on connect and clears stale ephemeral browser state
  - streamed assistant text accumulates in `streamingText`
  - tool calls are tracked separately from plain chat messages
  - permission requests open a modal that round-trips `permission_response`
  - runtime snapshots update token usage from the shared backend runtime instead of browser-local estimation
- Browser interrupt should stay explainable and lightweight:
  - the frontend sends an `interrupt` WebSocket message
  - the backend tracks and cancels the active agent task rather than inventing a second agent loop
  - cancellation is surfaced through the existing `error` + `agent_end` flow so the UI clears streaming state without hiding the raw interruption signal
  - user-triggered interruption is a normal operator action, so the browser may render it as a system/error message in the transcript but should avoid treating it like an unexpected console failure
  - the chat input swaps its send affordance for an explicit stop control while streaming is active
- REST endpoints provide supporting panel data for tools, MCP status, hooks, diagnostics, model profiles, config, and command metadata.
- WebUI runtime snapshots now also include loaded repo-local extension metadata, and `/api/extensions` exposes the same extension list for browser consumers.
- Browser-shell polish belongs to this feature when it affects live verification:
  - the served HTML shell should include a stable favicon reference so normal page loads do not produce avoidable 404 noise
  - browser console output should reserve `error` logging for real failures rather than expected user-driven terminal states

## Open Questions

- Reconnect still restores a usable socket and the latest transcript snapshot, but it does not attempt to resume an in-flight stream or reconstruct transient tool-progress UI from a previous connection.

## Verification

- If backend protocol changes, run the relevant backend tests plus a manual WebUI smoke check.
- If frontend state handling changes, verify:
  - initial connect hydrates historical messages into the chat timeline
  - message send still appends an optimistic user message
  - tool-call start and end cards still update correctly
  - permission prompts still appear and clear
  - interrupt clears the active stream and leaves the transcript in a readable terminal state
  - interrupt does not create avoidable browser-console error noise for expected user cancellation
  - `/model` and other slash commands still return `command_response` events
  - reconnect still restores a working socket after disconnect
  - the served page loads without a missing-favicon 404

## Follow-ups

- If browser functionality expands much further, split chat transport, panel data hydration, and visual rendering into separate feature specs instead of keeping all browser concerns under one umbrella.
