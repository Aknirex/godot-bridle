from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from bridle.config.secrets import contains_forbidden_secret_field
from bridle.domain.errors import ConfigError
from bridle.domain.providers import ProviderConfig


class BridleConfig(BaseModel):
    providers: list[ProviderConfig] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def load_config(path: Path) -> BridleConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> BridleConfig:
    if contains_forbidden_secret_field(raw):
        raise ConfigError(
            "TOML config must not contain plaintext secret fields. Use api_key_env instead."
        )

    providers_raw = raw.get("providers", [])
    if not isinstance(providers_raw, list):
        raise ConfigError("providers must be a list of provider tables.")

    providers = [ProviderConfig.model_validate(item) for item in providers_raw]
    warnings = _duplicate_key_source_warnings(providers)
    return BridleConfig(providers=providers, warnings=warnings)


def _duplicate_key_source_warnings(providers: list[ProviderConfig]) -> list[str]:
    seen: dict[str, str] = {}
    warnings: list[str] = []
    for provider in providers:
        if provider.api_key_env is None:
            continue
        previous_provider_id = seen.get(provider.api_key_env)
        if previous_provider_id is not None:
            warnings.append(
                "api_key_env "
                f"{provider.api_key_env!r} is referenced by both "
                f"{previous_provider_id!r} and {provider.provider_id!r}."
            )
            continue
        seen[provider.api_key_env] = provider.provider_id
    return warnings
