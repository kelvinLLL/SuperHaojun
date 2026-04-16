---
title: Multi-Agent
status: active
owner: Haojun
last_updated: 2026-04-16
source_paths:
  - src/superhaojun/agents/sub_agent.py
  - src/superhaojun/agents/coordinator.py
  - src/superhaojun/agents/agent_tool.py
  - src/superhaojun/agents/commands.py
  - tests/test_agents.py
---

# Multi-Agent

## Goal

- Let the system delegate isolated subtasks to child agents.
- Provide both direct sub-agent execution and coordinator-driven task planning.

## Scope

- In scope:
  - `SubAgent` execution
  - structured sub-agent results
  - coordinator task fan-out
  - LLM-based task decomposition
  - tool and command entry points for multi-agent execution
- Out of scope:
  - remote agent infrastructure
  - shared memory across child agents
  - long-running durable workflow orchestration

## File Structure

- `src/superhaojun/agents/sub_agent.py`
  Responsibility: runs an isolated child agent and returns a structured result object.
- `src/superhaojun/agents/coordinator.py`
  Responsibility: executes task sets concurrently or sequentially and optionally asks an LLM to generate the task list.
- `src/superhaojun/agents/agent_tool.py`
  Responsibility: exposes sub-agent execution as a tool callable from the main agent.
- `src/superhaojun/agents/commands.py`
  Responsibility: exposes local control and status for the coordinator through slash commands.
- `tests/test_agents.py`
  Responsibility: verifies sub-agent result handling, coordinator planning flow, tool wrapping, and command behavior.

## Current Design

- `SubAgent` is implemented as a lightweight wrapper around the normal `Agent` class, using its own `MessageBus` and collecting text deltas into one output string.
- `SubAgentResult` is the contract returned to parent callers. It includes output, tool-call count, turns used, token count placeholder, success flag, and error text.
- `Coordinator.run()` limits concurrency with a semaphore and delegates each `TaskSpec` to a fresh `SubAgent`.
- `Coordinator.run_with_llm_planning()` asks the configured model to emit a JSON task list, then feeds those generated tasks back through the normal coordinator path.
- `AgentTool` makes this capability model-callable from within the main agent, while `/agents` exposes it for local operator control.

## Open Questions

- `SubAgent.turns_used` is now sourced from the child agent runtime so parent callers can see how many turns were actually consumed.
- `tokens_used`, `max_tokens`, and `inherit_permissions` are still intentionally narrow or placeholder-only for this slice and should be treated as follow-up work rather than a stable public contract.

## Verification

- Run `uv run pytest tests/test_agents.py -v`.
- When changing coordinator or sub-agent behavior, confirm:
  - failed child runs still produce structured failure output
  - `turns_used` reflects the child agent runtime instead of staying at the default placeholder
  - LLM planning still accepts JSON arrays and handles planning failures cleanly
  - the agent tool still delegates through `SubAgent`
  - `/agents` output remains aligned with coordinator state

## Follow-ups

- If multi-agent work becomes more central, consider splitting planning, execution, and reporting into separate files instead of deepening the current all-in-one coordinator path.
