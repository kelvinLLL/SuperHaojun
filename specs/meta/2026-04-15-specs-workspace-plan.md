# Specs Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a top-level `specs/` workspace for SDD documents and point future development toward it.

**Architecture:** Add a minimal directory skeleton, define the contract documents that drive feature work, and update the repo README so the new workspace is discoverable. Keep existing `docs/` content in place.

**Tech Stack:** Markdown documentation, repository structure, README guidance

---

### Task 1: Create the SDD workspace skeleton

**Files:**
- Create: `specs/README.md`
- Create: `specs/development-rules.md`
- Create: `specs/features/README.md`
- Create: `specs/references/doc-contract.md`
- Create: `specs/assets/feature-doc-template.md`

- [ ] **Step 1: Create the directory layout**

Run: `mkdir -p specs/{assets,features,references,meta}`
Expected: directories exist with no content errors

- [ ] **Step 2: Write the workspace entry doc**

Document the purpose of `specs/`, the override from generic SDD paths, and the default workflow.

- [ ] **Step 3: Write the core rules and contracts**

Document reusable rules, feature spec authoring guidance, the canonical doc contract, and the template used to create new feature specs.

- [ ] **Step 4: Review the structure**

Run: `find specs -maxdepth 3 \\( -type d -o -type f \\) | sort`
Expected: the new files and directories appear under `specs/`

### Task 2: Update project entry guidance

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a short SDD entry note**

Add a concise note that active development specs live in `specs/` while background architecture and analysis remain in `docs/`.

- [ ] **Step 2: Update the project structure block**

Include `specs/` in the top-level tree and describe its role.

- [ ] **Step 3: Review the diff**

Run: `git diff -- specs README.md`
Expected: the README and new docs reflect the new workspace without moving legacy content
