"""Model and provider configuration loaded from environment variables."""

import re
import ssl
from dataclasses import dataclass, field

from pydantic_settings import BaseSettings


class EnvConfig(BaseSettings):
    """Read config from .env / environment variables."""

    model_config = {"env_file": ".env", "extra": "ignore"}

    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"
    model_id: str = "gpt-4o"
    model_provider: str = "openai"


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model_id: str
    base_url: str
    api_key: str
    is_reasoning: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "is_reasoning",
            bool(re.search(r"o[1-9]|gpt-5", self.model_id)),
        )


def load_config() -> ModelConfig:
    env = EnvConfig()  # type: ignore[call-arg]
    return ModelConfig(
        provider=env.model_provider,
        model_id=env.model_id,
        base_url=env.openai_base_url,
        api_key=env.openai_api_key,
    )


def make_permissive_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that skips certificate verification.

    Used for personal proxy endpoints with CDN-issued certificates.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
