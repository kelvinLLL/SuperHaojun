---
title: Model Config
status: active
owner: Haojun
last_updated: 2026-04-15
source_paths:
  - src/superhaojun/config.py
  - tests/test_config.py
  - models.yaml
---

# Model Config

## Goal

- Resolve the active model endpoint and credentials for the agent.
- Support both simple local setup and runtime-switchable multi-model workflows.

## Scope

- In scope:
  - `.env` fallback loading
  - `models.yaml` profile loading
  - runtime `ModelRegistry` switching
  - reasoning-model detection
  - permissive SSL setup for proxy endpoints
- Out of scope:
  - provider-specific API clients beyond OpenAI-compatible usage
  - UI presentation details of model switching
  - request-time token accounting or retry policy

## File Structure

- `src/superhaojun/config.py`
  Responsibility: defines `EnvConfig`, `ModelConfig`, `ModelProfile`, `ModelRegistry`, config loading helpers, and SSL context creation.
- `models.yaml`
  Responsibility: optional project-level profile source for named model endpoints.
- `tests/test_config.py`
  Responsibility: verifies defaults, reasoning detection, environment loading, and permissive SSL behavior.

## Current Design

- Configuration loads through `load_model_registry()`, then `load_config()` returns the active profile for backward-compatible callers.
- Load order is:
  - explicit YAML path
  - `./models.yaml`
  - `~/.haojun/models.yaml`
  - `.env` / environment fallback
- `models.yaml` supports two shapes:
  - flat model entries with inline `base_url` and `api_key`
  - provider blocks plus model entries that inherit credentials from the provider
- `${ENV_VAR}` placeholders are resolved from the process environment first, then from the local `.env` file.
- `ModelConfig` is frozen and computes `is_reasoning` from the `model_id` pattern. The flag is later used by the agent loop to decide whether to send reasoning-related request options.
- `ModelRegistry.switch()` only changes the active key and returns a fresh `ModelConfig`. Consumers such as the CLI `/model` command and the WebUI model endpoints are responsible for applying the new config to a running agent.
- `make_permissive_ssl_context()` deliberately disables certificate verification for personal proxy setups and is used by both the main agent and multi-agent planner paths.

## Open Questions

- Config loading is intentionally permissive: missing API keys are allowed at load time and only fail later at request time. If future optimization wants earlier validation, this file is the contract boundary that should own it.

## Verification

- Run `uv run pytest tests/test_config.py -v`.
- When editing profile loading or switching behavior, also confirm:
  - `uv run superhaojun` still boots with `.env` only
  - WebUI model listing and activation still work against `/api/config/models`
  - `/model` CLI output still reflects the active profile

## Follow-ups

- If provider-specific behavior grows beyond OpenAI-compatible settings, split transport-specific options out of `config.py` instead of continuing to expand `ModelConfig` as a grab bag.
