# Specs Workspace

This directory is the active SDD workspace for `superhaojun`.

- Use `specs/` for documents that directly drive implementation.
- Use `docs/` for architecture notes, research, deep dives, and historical analysis.
- Do not move old `docs/` content here unless a live feature spec needs to absorb part of it.

## Path Override

The generic `sdd-feature-development` workflow assumes `docs/`, `references/`, and `assets/` paths. In this repo, the equivalent paths live under `specs/`:

- `specs/development-rules.md`
- `specs/features/README.md`
- `specs/references/doc-contract.md`
- `specs/assets/feature-doc-template.md`

## Default Workflow

1. Read `specs/development-rules.md`.
2. Read `specs/features/README.md`.
3. Open or create the relevant file in `specs/features/`.
4. Update the feature spec before code.
5. Implement the change.
6. Update the feature spec again so it matches the final code.
7. Promote reusable lessons into `specs/development-rules.md`.

## Layout

```text
specs/
├── README.md
├── development-rules.md
├── features/
├── references/
├── assets/
└── meta/
```

- `features/` holds active feature specs.
- `references/` holds durable documentation contracts and shared reference material.
- `assets/` holds templates used to create new specs.
- `meta/` holds design and planning docs for the SDD workspace itself.
