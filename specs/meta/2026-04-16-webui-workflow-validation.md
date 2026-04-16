---
title: WebUI Workflow Validation
date: 2026-04-16
owner: Codex
status: completed
---

# WebUI Workflow Validation

## Goal

- Validate a set of common, high-signal workflows in the production WebUI.
- Use the repo's configured MiniMax M2 profile in the browser and capture evidence with screenshots.
- Fix any product issues surfaced during live verification and update the active spec in the same work.

## Model Choice

- The repo does not currently ship an exact `m2.5` profile in `models.yaml`.
- Validation used the configured MiniMax M2 profile exposed in the UI:
  - `Minimax-M2.7`
  - provider: `openrouter`
  - model id: `minimax/minimax-m2.7`

## Workflows

### 1. Live Model Switch

- Switched the active browser model from the default profile to `MiniMax: MiniMax M2.7`.
- Verified that the active model updated in-place without reloading the page.
- Screenshot:
  - `output/playwright/workflow-01-model-switch.png`

### 2. Command-Driven Control Plane

- Ran `/extensions` to confirm repo-local workflow rules were loaded.
- Ran `/memory add user Prefer concise bullet summaries during workflow validation.` to verify browser-side slash commands, persistent memory, and command echo behavior.
- Screenshot:
  - `output/playwright/workflow-02-extensions-memory.png`

### 3. Explainability During Tool Use

- Asked a repo question that caused the agent to call multiple tools (`read_file`, `grep`, `glob`) while the sidebar exposed status, token estimates, and message counters.
- Verified that raw tool activity remained visible instead of collapsing into a black-box summary.
- Screenshot:
  - `output/playwright/workflow-03-runtime-tools.png`

### 4. Interrupt Flow

- Interrupted an in-flight browser turn and confirmed that the transcript kept the raw `Interrupted by user.` terminal signal.
- Captured the pre-fix behavior during the original run, then re-validated after the browser-log polish fix.
- Screenshots:
  - `output/playwright/workflow-04-interrupt.png`
  - `output/playwright/workflow-06-interrupt-fixed.png`

### 5. Raw Transcript Inspection

- Switched to `Messages` and verified that the WebUI exposed raw transcript/tool envelopes instead of only rendered chat bubbles.
- Screenshot:
  - `output/playwright/workflow-05-messages-view.png`

## Issues Found

### Missing favicon

- Symptom:
  - every fresh WebUI load emitted a `GET /favicon.ico` 404 in the browser console
- Root cause:
  - the Vite HTML shell did not include a favicon reference, and no favicon asset existed in the built static bundle
- Fix:
  - added `webui/public/favicon.svg`
  - linked it from `webui/index.html`
  - rebuilt the production frontend so the served static bundle now includes `/favicon.svg`

### Interrupt logged as browser error

- Symptom:
  - `Interrupted by user.` was being logged with `console.error`, which made an expected operator action look like a frontend failure
- Root cause:
  - the WebSocket hook treated every `error` protocol message as a console error
- Fix:
  - kept the transcript/system message behavior intact
  - downgraded known expected terminal messages such as `Interrupted by user.` to `console.info`

## Non-Issues / Notes

- Repeated `/api/tasks` and `/api/overview` 404 traffic was observed in the backend log, but code inspection showed the current WebUI does not request those routes. This was treated as external noise, likely from another local client or stale browser state.
- One MiniMax run surfaced an upstream `500 Internal Server Error`. The app exposed the failure cleanly in chat, but this was treated as provider-side instability rather than an in-repo WebUI defect because the same model profile also completed other prompts successfully in the same session.

## Verification

- Automated:
  - `uv run pytest tests/test_webui_static.py tests/test_webui_server.py -q`
  - `npm run build`
- Manual / browser:
  - production WebUI loaded at `http://127.0.0.1:8765`
  - model switch succeeded in-place
  - `/extensions` and `/memory add ...` succeeded in chat
  - tool-call visibility, status panel updates, and raw transcript view were confirmed
  - after the frontend reload, the console no longer showed the missing favicon error
  - after the frontend reload, a scripted interrupt emitted `[Agent Status] Interrupted by user.` instead of `[Agent Error]`

## Outcome

- The current WebUI is strong at:
  - live model switching
  - command-driven control operations
  - explainable tool activity and runtime state
  - raw transcript inspection
  - operator-controlled interruption
- The live browser validation also improved product polish by removing avoidable console noise without weakening the existing explainability surface.
