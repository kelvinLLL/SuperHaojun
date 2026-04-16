---
title: LSP Feedback
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/lsp/client.py
  - src/superhaojun/lsp/diagnostics.py
  - src/superhaojun/lsp/managed.py
  - src/superhaojun/lsp/service.py
  - src/superhaojun/webui/server.py
  - tests/test_lsp.py
---

# LSP Feedback

## Goal

- Surface code intelligence and diagnostics to the agent and UI.
- Keep language-server failures from taking down the surrounding workflow.

## Scope

- In scope:
  - base LSP client usage
  - managed restart wrapper
  - diagnostic aggregation and deduplication
  - prompt-context summary generation
  - WebUI diagnostics exposure
- Out of scope:
  - editor plugins
  - file watching beyond explicit open or change flows
  - automated fix application

## File Structure

- `src/superhaojun/lsp/client.py`
  Responsibility: handles low-level LSP protocol operations for one server.
- `src/superhaojun/lsp/managed.py`
  Responsibility: adds restart state management and recovery behavior around a client instance.
- `src/superhaojun/lsp/diagnostics.py`
  Responsibility: aggregates and deduplicates diagnostics across providers and files.
- `src/superhaojun/lsp/service.py`
  Responsibility: coordinates language-specific clients and exposes high-level hover, definition, and diagnostics operations.
- `src/superhaojun/webui/server.py`
  Responsibility: exposes diagnostics through `/api/diagnostics`.
- `tests/test_lsp.py`
  Responsibility: verifies registry deduplication, managed restart behavior, and service-level operations.

## Current Design

- There are two adjacent layers:
  - `LSPService` manages multiple language-specific client instances
  - `ManagedLSPClient` adds crash recovery and restart backoff around a single client
- `DiagnosticRegistry` is the durable aggregation boundary. It deduplicates diagnostics by `(file, line, message)` even when different providers report the same issue.
- The registry accepts both:
  - native LSP diagnostics
  - injected diagnostics from hooks or external tools
- `to_prompt_context()` on the registry emits a compact error summary that can be injected into future prompts.
- `LSPService` also provides its own prompt-context summary, focused on running server state and error counts.
- The WebUI server exposes diagnostics as structured JSON, so the browser can render them without understanding raw LSP protocol messages.

## Open Questions

- The service layer and the managed restart wrapper are not yet fully unified. Future optimization should decide whether `LSPService` should own `ManagedLSPClient` instances directly instead of mixing raw-client and managed-client concepts.

## Next Slice

- Close the service boundary by having `LSPService` own `ManagedLSPClient` instances directly.
- Expose diagnostics through public snapshot methods on the client wrappers instead of reading `_diagnostics` internals.
- Use `DiagnosticRegistry` as the aggregation layer for service-level prompt context so duplicate diagnostics collapse before they reach the agent.

## Verification

- Run `uv run pytest tests/test_lsp.py -v`.
- When changing diagnostics aggregation or restart behavior, confirm:
  - duplicate diagnostics from different providers still collapse correctly
  - restart backoff still stops after `max_restarts`
  - prompt-context summaries remain bounded and readable
  - `/api/diagnostics` still returns file, location, severity, and provider fields

## Follow-ups

- If diagnostics start driving automatic remediation, split reporting from action selection instead of embedding repair policy into the registry itself.
