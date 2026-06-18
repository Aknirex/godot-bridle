from __future__ import annotations

import pytest

from bridle.config.key_resolver import KeyResolver
from bridle.domain.errors import AuthError
from bridle.domain.providers import ProviderConfig, ProviderKind


def test_key_resolver_reads_configured_env_var() -> None:
    provider = ProviderConfig(
        provider_id="deepseek",
        kind=ProviderKind.LLM,
        api_key_env="DEEPSEEK_API_KEY",
    )

    assert KeyResolver({"DEEPSEEK_API_KEY": "sk-test"}).resolve_required(provider) == "sk-test"


def test_key_resolver_rejects_missing_key() -> None:
    provider = ProviderConfig(
        provider_id="deepseek",
        kind=ProviderKind.LLM,
        api_key_env="DEEPSEEK_API_KEY",
    )

    with pytest.raises(AuthError, match="is not set"):
        KeyResolver({}).resolve_required(provider)


def test_key_resolver_describes_masked_source() -> None:
    provider = ProviderConfig(
        provider_id="deepseek",
        kind=ProviderKind.LLM,
        api_key_env="DEEPSEEK_API_KEY",
    )

    assert KeyResolver({"DEEPSEEK_API_KEY": "sk-1234567890"}).describe_source(provider) == (
        "DEEPSEEK_API_KEY=sk-1...7890"
    )
