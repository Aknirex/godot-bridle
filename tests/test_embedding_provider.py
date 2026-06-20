from __future__ import annotations

import os

import pytest

from bridle.config.key_resolver import KeyResolver
from bridle.domain.errors import AuthError, ProviderError
from bridle.domain.providers import ProviderConfig, ProviderKind
from bridle.providers.embedding_litellm import LiteLlmEmbeddingProvider


def embedding_config(*, model: str | None = "text-embedding-3-small") -> ProviderConfig:
    return ProviderConfig(
        provider_id="openai_embedding",
        kind=ProviderKind.LLM,
        backend="litellm",
        model=model,
        api_key_env="OPENAI_API_KEY",
    )


async def test_embedding_provider_returns_empty_batch_without_key() -> None:
    provider = LiteLlmEmbeddingProvider(embedding_config(), KeyResolver({}))

    assert await provider.embed([]) == []


async def test_embedding_provider_requires_key_before_network_call() -> None:
    provider = LiteLlmEmbeddingProvider(embedding_config(), KeyResolver({}))

    with pytest.raises(AuthError):
        await provider.embed(["project context"])


async def test_embedding_provider_calls_litellm_compatible_facade(monkeypatch) -> None:
    captured = {}

    async def fake_embedding(**kwargs):
        captured.update(kwargs)
        return {"data": [{"embedding": [0.25, 0.75]}, {"embedding": [1.0, 0.0]}]}

    monkeypatch.setattr("bridle.providers.embedding_litellm.litellm.aembedding", fake_embedding)
    provider = LiteLlmEmbeddingProvider(
        embedding_config(),
        KeyResolver({"OPENAI_API_KEY": "sk-private-test"}),
    )

    vectors = await provider.embed(["first", "second"])

    assert vectors == [[0.25, 0.75], [1.0, 0.0]]
    assert captured == {
        "model": "text-embedding-3-small",
        "input": ["first", "second"],
        "api_key": "sk-private-test",
    }


async def test_embedding_provider_hides_sdk_error_details(monkeypatch) -> None:
    async def fake_embedding(**kwargs):
        raise RuntimeError(f"rejected {kwargs['api_key']}")

    monkeypatch.setattr("bridle.providers.embedding_litellm.litellm.aembedding", fake_embedding)
    provider = LiteLlmEmbeddingProvider(
        embedding_config(),
        KeyResolver({"OPENAI_API_KEY": "sk-private-test"}),
    )

    with pytest.raises(ProviderError) as captured:
        await provider.embed(["secret-safe"])

    assert "sk-private-test" not in captured.value.safe_details


async def test_embedding_provider_rejects_invalid_response(monkeypatch) -> None:
    async def fake_embedding(**kwargs):
        return {"data": []}

    monkeypatch.setattr("bridle.providers.embedding_litellm.litellm.aembedding", fake_embedding)
    provider = LiteLlmEmbeddingProvider(
        embedding_config(),
        KeyResolver({"OPENAI_API_KEY": "sk-private-test"}),
    )

    with pytest.raises(ProviderError, match="invalid response"):
        await provider.embed(["missing vector"])


async def test_embedding_provider_batches_requests(monkeypatch) -> None:
    batches = []

    async def fake_embedding(**kwargs):
        batches.append(list(kwargs["input"]))
        return {"data": [{"embedding": [1.0]} for _ in kwargs["input"]]}

    monkeypatch.setattr("bridle.providers.embedding_litellm.litellm.aembedding", fake_embedding)
    provider = LiteLlmEmbeddingProvider(
        embedding_config(),
        KeyResolver({"OPENAI_API_KEY": "sk-private-test"}),
        batch_size=2,
    )

    await provider.embed(["one", "two", "three"])

    assert batches == [["one", "two"], ["three"]]


def test_embedding_index_identity_changes_with_model() -> None:
    first = LiteLlmEmbeddingProvider(embedding_config(model="first"))
    second = LiteLlmEmbeddingProvider(embedding_config(model="second"))

    assert first.index_identity != second.index_identity


@pytest.mark.external_api
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY is required for embedding smoke test.",
)
async def test_openai_embedding_smoke() -> None:
    provider = LiteLlmEmbeddingProvider(embedding_config())

    vectors = await provider.embed(["Godot project context"])

    assert len(vectors) == 1
    assert vectors[0]
