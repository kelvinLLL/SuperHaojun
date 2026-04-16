"""Tests for shared runtime assembly."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from superhaojun.config import ModelProfile, ModelRegistry
from superhaojun.runtime import build_runtime


def _make_registry() -> ModelRegistry:
    return ModelRegistry(
        profiles={
            "default": ModelProfile(
                key="default",
                name="Default",
                model_id="gpt-4o",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
            ),
        },
        _active_key="default",
    )


def test_build_runtime_includes_full_command_dependencies(tmp_path: Path) -> None:
    with patch("superhaojun.runtime.load_mcp_configs", return_value=[]):
        runtime = build_runtime(
            working_dir=tmp_path,
            model_registry=_make_registry(),
        )

    ctx = runtime.build_command_context()

    assert ctx.agent is runtime.agent
    assert ctx.command_registry is runtime.command_registry
    assert ctx.model_registry is runtime.model_registry
    assert ctx.session_manager is runtime.session_manager
    assert ctx.memory_store is runtime.memory_store
    assert ctx.mcp_manager is runtime.mcp_manager
    assert ctx.extension_runtime is runtime.extension_runtime


def test_build_runtime_uses_brand_root_inside_working_dir(tmp_path: Path) -> None:
    with patch("superhaojun.runtime.load_mcp_configs", return_value=[]):
        runtime = build_runtime(
            working_dir=tmp_path,
            model_registry=_make_registry(),
        )

    assert runtime.brand_root.parent == tmp_path
    assert runtime.session_manager is not None
    assert runtime.memory_store is not None
    assert runtime.mcp_manager is not None
