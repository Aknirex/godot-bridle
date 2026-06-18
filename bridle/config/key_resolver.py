from __future__ import annotations

import os
from collections.abc import Mapping

from bridle.config.secrets import mask_secret
from bridle.domain.errors import AuthError
from bridle.domain.providers import ProviderConfig


class KeyResolver:
    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def resolve_required(self, provider: ProviderConfig) -> str:
        if provider.api_key_env is None:
            raise AuthError(f"Provider {provider.provider_id!r} has no api_key_env configured.")
        value = self._environ.get(provider.api_key_env)
        if not value:
            raise AuthError(
                f"Environment variable {provider.api_key_env!r} is not set "
                f"for provider {provider.provider_id!r}."
            )
        return value

    def describe_source(self, provider: ProviderConfig) -> str:
        if provider.api_key_env is None:
            return "no api_key_env"
        value = self._environ.get(provider.api_key_env)
        masked = mask_secret(value)
        if masked is None:
            return f"{provider.api_key_env}=<unset>"
        return f"{provider.api_key_env}={masked}"
