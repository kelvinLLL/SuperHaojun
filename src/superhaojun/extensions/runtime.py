"""Repo-local extension discovery and control."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..constants import BRAND_DIR, INSTRUCTION_FILES


@dataclass
class ExtensionEntry:
    """A single discovered repo-local extension source."""

    id: str
    kind: str
    name: str
    source: str
    scope: str
    enabled: bool
    prompt_enabled: bool
    prompt_text: str = ""

    def to_dict(self, *, include_prompt_text: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "source": self.source,
            "scope": self.scope,
            "enabled": self.enabled,
            "prompt_enabled": self.prompt_enabled,
        }
        if include_prompt_text:
            data["prompt_text"] = self.prompt_text
        return data


class ExtensionRuntime:
    """Thin repo-local runtime for prompt-capable and metadata-only extensions."""

    def __init__(
        self,
        working_dir: str | Path,
        *,
        config_path: str | Path | None = None,
    ) -> None:
        self.working_dir = Path(working_dir).resolve()
        self.config_path = (
            Path(config_path).resolve()
            if config_path is not None
            else (self.working_dir / BRAND_DIR / "extensions.json").resolve()
        )
        self._entries: list[ExtensionEntry] = []
        self.reload()

    def reload(self) -> None:
        overrides = self._load_overrides()
        entries = self._discover_entries()
        for entry in entries:
            override = overrides.get(entry.id, {})
            enabled = override.get("enabled")
            if isinstance(enabled, bool):
                entry.enabled = enabled
        self._entries = entries

    def list_extensions(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self._entries]

    def prompt_entries(self) -> list[dict[str, Any]]:
        return [entry.to_dict(include_prompt_text=True) for entry in self._entries]

    def prompt_text(self) -> str:
        blocks = []
        for entry in self._entries:
            if not entry.enabled or not entry.prompt_enabled or not entry.prompt_text:
                continue
            blocks.append(entry.prompt_text)
        return "\n\n".join(blocks)

    def enable(self, extension_id: str) -> bool:
        return self._set_enabled(extension_id, True)

    def disable(self, extension_id: str) -> bool:
        return self._set_enabled(extension_id, False)

    def _set_enabled(self, extension_id: str, enabled: bool) -> bool:
        for entry in self._entries:
            if entry.id != extension_id:
                continue
            entry.enabled = enabled
            overrides = self._load_overrides()
            overrides[extension_id] = {"enabled": enabled}
            self._save_overrides(overrides)
            return True
        return False

    def _discover_entries(self) -> list[ExtensionEntry]:
        entries: list[ExtensionEntry] = []
        entries.extend(self._discover_instruction_entries())

        rules_path = self._find_development_rules()
        if rules_path is not None:
            text = rules_path.read_text(encoding="utf-8").strip()
            if text:
                source = self._display_path(rules_path)
                entries.append(
                    ExtensionEntry(
                        id=f"workflow_rules:{source}",
                        kind="workflow_rules",
                        name=rules_path.name,
                        source=source,
                        scope="repo",
                        enabled=True,
                        prompt_enabled=True,
                        prompt_text=text,
                    )
                )

        hooks_path = self.working_dir / BRAND_DIR / "hooks.json"
        if hooks_path.is_file():
            source = self._display_path(hooks_path)
            summary = self._summarize_hooks(hooks_path)
            entries.append(
                ExtensionEntry(
                    id=f"hook_rules:{source}",
                    kind="hook_rules",
                    name=hooks_path.name,
                    source=source,
                    scope="brand",
                    enabled=True,
                    prompt_enabled=False,
                    prompt_text=summary,
                )
            )

        return entries

    def _discover_instruction_entries(self) -> list[ExtensionEntry]:
        entries: list[ExtensionEntry] = []
        seen_paths: set[Path] = set()
        ancestors: list[Path] = []
        current = self.working_dir

        while True:
            ancestors.append(current)
            parent = current.parent
            if parent == current:
                break
            current = parent

        for dir_path in reversed(ancestors):
            search_dirs = [dir_path]
            brand_dir = dir_path / BRAND_DIR
            if brand_dir.is_dir():
                search_dirs.append(brand_dir)

            for search_dir in search_dirs:
                for filename in INSTRUCTION_FILES:
                    filepath = (search_dir / filename).resolve()
                    if filepath in seen_paths or not filepath.is_file():
                        continue
                    seen_paths.add(filepath)
                    text = filepath.read_text(encoding="utf-8").strip()
                    if not text:
                        continue
                    source = self._display_path(filepath)
                    scope = "brand" if search_dir.name == BRAND_DIR else (
                        "repo" if dir_path == self.working_dir else "ancestor"
                    )
                    entries.append(
                        ExtensionEntry(
                            id=f"instruction:{source}",
                            kind="instruction",
                            name=filepath.name,
                            source=source,
                            scope=scope,
                            enabled=True,
                            prompt_enabled=True,
                            prompt_text=text,
                        )
                    )
        return entries

    def _find_development_rules(self) -> Path | None:
        current = self.working_dir
        while True:
            candidate = current / "specs" / "development-rules.md"
            if candidate.is_file():
                return candidate.resolve()
            parent = current.parent
            if parent == current:
                return None
            current = parent

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.working_dir))
        except ValueError:
            return str(path)

    def _summarize_hooks(self, path: Path) -> str:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return ""
        hooks = data.get("hooks", [])
        if not isinstance(hooks, list):
            return ""
        return f"Loaded hook config with {len(hooks)} rules."

    def _load_overrides(self) -> dict[str, dict[str, Any]]:
        if not self.config_path.is_file():
            return {}
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        extensions = data.get("extensions", {})
        if not isinstance(extensions, dict):
            return {}
        return {
            str(key): value
            for key, value in extensions.items()
            if isinstance(value, dict)
        }

    def _save_overrides(self, overrides: dict[str, dict[str, Any]]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"extensions": overrides}
        self.config_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
