"""Tests for repo-local extension runtime."""

from __future__ import annotations

import json
from pathlib import Path

from superhaojun.extensions.runtime import ExtensionRuntime


def test_discovers_repo_local_extensions(tmp_path: Path) -> None:
    (tmp_path / "SUPERHAOJUN.md").write_text("Use dataclasses.", encoding="utf-8")
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "development-rules.md").write_text(
        "Explainability First.",
        encoding="utf-8",
    )
    brand = tmp_path / ".haojun"
    brand.mkdir()
    (brand / "hooks.json").write_text(json.dumps({"hooks": []}), encoding="utf-8")

    runtime = ExtensionRuntime(working_dir=tmp_path, config_path=brand / "extensions.json")
    extensions = runtime.list_extensions()

    assert [item["kind"] for item in extensions] == [
        "instruction",
        "workflow_rules",
        "hook_rules",
    ]
    assert runtime.prompt_text()
    assert "Use dataclasses." in runtime.prompt_text()
    assert "Explainability First." in runtime.prompt_text()
    hook_entry = next(item for item in extensions if item["kind"] == "hook_rules")
    assert hook_entry["prompt_enabled"] is False


def test_disable_extension_persists_and_removes_prompt_text(tmp_path: Path) -> None:
    (tmp_path / "SUPERHAOJUN.md").write_text("Use dataclasses.", encoding="utf-8")
    brand = tmp_path / ".haojun"
    brand.mkdir()

    config_path = brand / "extensions.json"
    runtime = ExtensionRuntime(working_dir=tmp_path, config_path=config_path)
    extension_id = runtime.list_extensions()[0]["id"]

    assert runtime.disable(extension_id) is True
    assert "Use dataclasses." not in runtime.prompt_text()

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["extensions"][extension_id]["enabled"] is False

    reloaded = ExtensionRuntime(working_dir=tmp_path, config_path=config_path)
    extension = reloaded.list_extensions()[0]
    assert extension["enabled"] is False
    assert "Use dataclasses." not in reloaded.prompt_text()
