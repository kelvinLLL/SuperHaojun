"""Model and provider configuration.

Supports two loading modes:
- models.yaml (preferred): define multiple named profiles, switch at runtime
- .env fallback: single-model config via environment variables
"""

from __future__ import annotations

import os
import re
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings


# ── Single-model env fallback ──────────────────────────────────────────────

class EnvConfig(BaseSettings):
    """Read single-model config from .env / environment variables."""

    model_config = {"env_file": ".env", "extra": "ignore"}

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    model_id: str = "gpt-4o"
    model_provider: str = "openai"
    model_api: str = "openai-completions"


# ── Core model config ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class ModelConfig:
    """Runtime config for a single LLM endpoint."""

    provider: str
    model_id: str
    base_url: str
    api_key: str
    api_type: str = "openai-completions"
    is_reasoning: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "is_reasoning",
            bool(re.search(r"o[1-9]|gpt-5|step-3|deepseek-r", self.model_id)),
        )


# ── Multi-model registry ───────────────────────────────────────────────────

@dataclass
class ModelProfile:
    """A named model profile from models.yaml."""

    key: str           # identifier used in models.yaml
    name: str          # display name shown in UI
    model_id: str
    base_url: str
    api_key: str
    provider: str = "openai"

    def to_config(self) -> ModelConfig:
        return ModelConfig(
            provider=self.provider,
            model_id=self.model_id,
            base_url=self.base_url,
            api_key=self.api_key,
        )


@dataclass
class ModelRegistry:
    """Holds all model profiles loaded from models.yaml.

    Provides the active model config and allows runtime switching.
    """

    profiles: dict[str, ModelProfile] = field(default_factory=dict)
    _active_key: str = field(default="")

    @property
    def active_key(self) -> str:
        return self._active_key

    @property
    def active(self) -> ModelConfig:
        profile = self.profiles.get(self._active_key)
        if profile is None:
            raise RuntimeError(f"No active model profile '{self._active_key}'")
        return profile.to_config()

    def switch(self, key: str) -> ModelConfig:
        """Switch active model. Returns the new ModelConfig."""
        if key not in self.profiles:
            raise ValueError(f"Unknown model profile '{key}'. Available: {list(self.profiles)}")
        self._active_key = key
        return self.active

    def list_profiles(self) -> list[dict[str, Any]]:
        """Serializable list of all profiles with active flag."""
        return [
            {
                "key": k,
                "name": p.name,
                "model_id": p.model_id,
                "base_url": p.base_url,
                "provider": p.provider,
                "active": k == self._active_key,
            }
            for k, p in self.profiles.items()
        ]


def _resolve_env_vars(value: str) -> str:
    """Resolve ${VAR_NAME} references in a string to environment variables."""
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        resolved = os.environ.get(var_name, "")
        if not resolved:
            # Also try loading from .env manually
            env_file = Path(".env")
            if env_file.is_file():
                for line in env_file.read_text().splitlines():
                    line = line.strip()
                    if line.startswith(var_name + "=") and not line.startswith("#"):
                        resolved = line.split("=", 1)[1].split("#")[0].strip()
                        break
        return resolved

    return re.sub(r"\$\{([^}]+)\}", replacer, value)


def load_model_registry(
    yaml_path: Path | None = None,
) -> ModelRegistry:
    """Load ModelRegistry from models.yaml.

    Falls back to .env single-model config if no yaml found.
    Search order:
    1. yaml_path (explicit)
    2. ./models.yaml (project root)
    3. ~/.haojun/models.yaml (user global)
    4. .env fallback
    """
    # Try to import PyYAML
    try:
        import yaml
    except ImportError:
        yaml = None  # type: ignore[assignment]

    candidates: list[Path] = []
    if yaml_path:
        candidates.append(yaml_path)
    candidates.append(Path("models.yaml"))
    candidates.append(Path.home() / ".haojun" / "models.yaml")

    if yaml is not None:
        for path in candidates:
            if path.is_file():
                return _load_from_yaml(path, yaml)

    # .env fallback
    return _load_from_env()


def _load_from_yaml(path: Path, yaml: Any) -> ModelRegistry:
    """Parse models.yaml into a ModelRegistry.

    Supports two formats:
    - Flat: each model entry has its own base_url + api_key
    - Two-level: shared providers block, model entries reference provider by name
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    default_key = raw.get("default", "")
    models_raw = raw.get("models", {})
    providers_raw = raw.get("providers", {})

    # Resolve provider credentials
    resolved_providers: dict[str, dict[str, str]] = {}
    for pname, pentry in providers_raw.items():
        if not isinstance(pentry, dict):
            continue
        resolved_providers[pname] = {
            "base_url": pentry.get("base_url", "https://api.openai.com/v1"),
            "api_key": _resolve_env_vars(pentry.get("api_key", "")),
        }

    profiles: dict[str, ModelProfile] = {}
    for key, entry in models_raw.items():
        if not isinstance(entry, dict):
            continue

        provider_name = entry.get("provider", "openai")

        # Two-level: look up provider block for credentials
        if provider_name in resolved_providers:
            pdata = resolved_providers[provider_name]
            base_url = entry.get("base_url") or pdata["base_url"]
            api_key = _resolve_env_vars(entry.get("api_key", "")) or pdata["api_key"]
        else:
            # Flat: credentials inline on the model entry
            base_url = entry.get("base_url", "https://api.openai.com/v1")
            api_key = _resolve_env_vars(entry.get("api_key", ""))

        profiles[key] = ModelProfile(
            key=key,
            name=entry.get("name", key),
            model_id=entry.get("model_id", ""),
            base_url=base_url,
            api_key=api_key,
            provider=provider_name,
        )

    active_key = default_key if default_key in profiles else (next(iter(profiles)) if profiles else "")
    registry = ModelRegistry(profiles=profiles)
    registry._active_key = active_key
    return registry


def _load_from_env() -> ModelRegistry:
    """Build a single-profile registry from .env / environment variables."""
    env = EnvConfig()  # type: ignore[call-arg]
    key = "default"
    profile = ModelProfile(
        key=key,
        name=f"{env.model_id} ({env.model_provider})",
        model_id=env.model_id,
        base_url=env.openai_base_url,
        api_key=env.openai_api_key,
        provider=env.model_provider,
    )
    registry = ModelRegistry(profiles={key: profile})
    registry._active_key = key
    return registry


def load_config() -> ModelConfig:
    """Load a single ModelConfig (backward-compatible entry point)."""
    return load_model_registry().active


def make_permissive_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that skips certificate verification.

    Used for personal proxy endpoints with CDN-issued certificates.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
