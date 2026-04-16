---
title: Session Persistence
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/session/manager.py
  - src/superhaojun/commands/builtins.py
  - src/superhaojun/main.py
  - tests/test_session.py
---

# Session Persistence

## Goal

- Preserve chat history across process restarts.
- Make session storage resilient enough that partial progress survives crashes.

## Scope

- In scope:
  - session metadata
  - JSONL storage format
  - append-and-flush writer behavior
  - backward compatibility with legacy JSON sessions
  - manual CLI session save/load/list/delete flows
- Out of scope:
  - automatic resume UX
  - memory extraction from saved sessions
  - remote or shared session backends

## File Structure

- `src/superhaojun/session/manager.py`
  Responsibility: defines `SessionInfo`, `SessionWriter`, and `SessionManager`, and owns storage compatibility rules.
- `src/superhaojun/commands/builtins.py`
  Responsibility: exposes manual `/session` operations to the CLI layer.
- `src/superhaojun/main.py`
  Responsibility: creates the session manager at startup and threads it into command execution context.
- `tests/test_session.py`
  Responsibility: verifies JSONL behavior, CRUD operations, crash-safe writes, and legacy compatibility.

## Current Design

- New session files are stored as JSONL:
  - first line is a header object
  - each later line is one serialized `ChatMessage`
- `SessionWriter` opens files lazily, creates parent directories, and flushes every write so on-disk state stays current even if the process exits unexpectedly.
- `SessionManager.save()` performs a full rewrite into JSONL and removes a legacy `.json` file if one exists for the same session name.
- `SessionManager.create_writer()` supports append-oriented flows, but current CLI wiring primarily uses save/load style commands rather than always-on incremental session capture.
- `load()` and `list_sessions()` remain backward compatible with older JSON session files.
- Session names are sanitized through `_safe_name()` so user-facing labels can still map to filesystem-safe filenames.

## Open Questions

- The storage layer supports incremental writing, but the main REPL does not yet treat session recording as an always-on runtime feature. If future optimization wants automatic crash-safe session capture, this is the boundary to extend.

## Verification

- Run `uv run pytest tests/test_session.py -v`.
- Manually verify `/session save <name>` and `/session load <name>` after changing storage format behavior.
- When editing persistence rules, confirm:
  - header plus message JSONL format is preserved
  - rewrites still remove legacy `.json` files
  - corrupted JSONL lines are skipped rather than crashing load
  - session summaries remain visible in listed metadata

## Follow-ups

- If session metadata expands, keep the header line authoritative rather than duplicating state across multiple files.
