# Feature Doc Contract

Use this contract for every file in `specs/features/`.

## Header Metadata

Every feature spec starts with front matter:

```yaml
---
title: <Feature title>
status: draft
owner: <name or team>
last_updated: YYYY-MM-DD
source_paths:
  - path/to/code
---
```

## Required Sections

### Goal

- What this feature is for.
- Why it exists now.

### Scope

- What this spec covers.
- What it intentionally does not cover.

### File Structure

- List the main files or directories involved.
- Explain the responsibility of each item.
- Use this section to make boundaries clear before code changes.

### Current Design

- Describe the current flow, key objects, and important decisions.
- Keep it grounded in the code that exists or is about to exist.

## Recommended Sections

- `Open Questions`
- `Verification`
- `Follow-ups`

## Update Rule

If implementation changes the active design, boundary, or file ownership, update the feature spec in the same work.
