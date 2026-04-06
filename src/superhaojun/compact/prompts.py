"""Structured compaction prompt templates (inspired by Claude Code's 9-section format)."""

COMPACTION_SYSTEM_PROMPT = """\
You are a conversation compactor. Your job is to produce a concise, structured \
summary of the conversation that preserves all critical context for continuing the work."""

COMPACTION_USER_PROMPT = """\
Analyze the following conversation and produce a structured summary.

## Instructions
1. Preserve ALL file paths, function names, variable names, and line numbers mentioned.
2. Preserve the user's original intent and any unresolved tasks.
3. Preserve all error messages and their solutions (or lack thereof).
4. Preserve decisions made and their rationale.
5. Track what tools were called and their key results.
6. Be concise — omit pleasantries, repetition, and exploratory dead ends.

## Output Format

### Primary Request and Intent
[What the user originally asked for and why]

### Key Technical Context
[Important file paths, code structures, architecture decisions]

### Files Modified or Read
[List of files with brief description of changes/content]

### Current Progress
[What has been completed, what remains]

### Errors and Resolutions
[Any errors encountered and how they were resolved]

### Active Decisions
[Design decisions, trade-offs chosen, constraints identified]

### Pending Tasks
[Unfinished work, next steps]

## Conversation to Summarize
{conversation}"""

SESSION_SUMMARY_PROMPT = """\
Produce a high-level summary of this entire session for future reference.
Focus on: what was accomplished, key decisions made, files changed, and any open items.
Keep it under 500 words.

Conversation:
{conversation}"""
