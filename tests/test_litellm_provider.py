from __future__ import annotations

import os

import pytest

from bridle.config.key_resolver import KeyResolver
from bridle.domain.errors import AuthError
from bridle.domain.providers import LlmChatRequest, ProviderConfig, ProviderKind
from bridle.providers.llm_litellm import LiteLlmProvider


async def test_litellm_provider_requires_key_before_network_call() -> None:
    provider = LiteLlmProvider(
        ProviderConfig(
            provider_id="deepseek",
            kind=ProviderKind.LLM,
            model="deepseek/deepseek-chat",
            api_key_env="DEEPSEEK_API_KEY",
        ),
        key_resolver=KeyResolver({}),
    )

    with pytest.raises(AuthError):
        await provider.chat(LlmChatRequest(messages=[]))


async def test_litellm_provider_reports_missing_model_as_config_error() -> None:
    provider = LiteLlmProvider(
        ProviderConfig(
            provider_id="deepseek",
            kind=ProviderKind.LLM,
            api_key_env="DEEPSEEK_API_KEY",
        ),
        key_resolver=KeyResolver({"DEEPSEEK_API_KEY": "sk-test"}),
    )

    health = await provider.test_connection()

    assert health.status == "config_error"
    assert "no model configured" in health.safe_details


@pytest.mark.external_api
@pytest.mark.skipif(
    not os.environ.get("DEEPSEEK_API_KEY"),
    reason="DEEPSEEK_API_KEY is required for DeepSeek smoke test.",
)
async def test_deepseek_smoke_chat() -> None:
    provider = LiteLlmProvider(
        ProviderConfig(
            provider_id="deepseek",
            kind=ProviderKind.LLM,
            model="deepseek/deepseek-chat",
            api_key_env="DEEPSEEK_API_KEY",
        )
    )

    response = await provider.chat(
        LlmChatRequest(
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
            max_tokens=8,
            temperature=0,
        )
    )

    assert response.content.strip()
