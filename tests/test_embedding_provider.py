from __future__ import annotations

import importlib.util
import os

import pytest

from bridle.config.key_resolver import KeyResolver
from bridle.domain.errors import AuthError, ProviderError
from bridle.domain.providers import ProviderConfig, ProviderKind
from bridle.providers.embedding_litellm import LiteLlmEmbeddingProvider

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("litellm") is None,
    reason="LiteLLM compatibility extra is not installed",
)


def embedding_config(
    *,
    model: str | None = "openai/test-embedding",
    base_url: str | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        provider_id="compatible_embedding",
        kind=ProviderKind.LLM,
        backend="litellm",
        model=model,
        base_url=base_url,
        api_key_env="EMBEDDING_API_KEY",
    )


def external_embedding_config() -> ProviderConfig:
    return embedding_config(
        model=os.environ.get("EMBEDDING_MODEL"),
        base_url=os.environ.get("EMBEDDING_API_BASE"),
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
        KeyResolver({"EMBEDDING_API_KEY": "sk-private-test"}),
    )

    vectors = await provider.embed(["first", "second"])

    assert vectors == [[0.25, 0.75], [1.0, 0.0]]
    assert captured == {
        "model": "openai/test-embedding",
        "input": ["first", "second"],
        "api_key": "sk-private-test",
    }


async def test_embedding_provider_hides_sdk_error_details(monkeypatch) -> None:
    async def fake_embedding(**kwargs):
        raise RuntimeError(f"rejected {kwargs['api_key']}")

    monkeypatch.setattr("bridle.providers.embedding_litellm.litellm.aembedding", fake_embedding)
    provider = LiteLlmEmbeddingProvider(
        embedding_config(),
        KeyResolver({"EMBEDDING_API_KEY": "sk-private-test"}),
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
        KeyResolver({"EMBEDDING_API_KEY": "sk-private-test"}),
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
        KeyResolver({"EMBEDDING_API_KEY": "sk-private-test"}),
        batch_size=2,
    )

    await provider.embed(["one", "two", "three"])

    assert batches == [["one", "two"], ["three"]]


def test_embedding_index_identity_changes_with_model() -> None:
    first = LiteLlmEmbeddingProvider(embedding_config(model="first"))
    second = LiteLlmEmbeddingProvider(embedding_config(model="second"))

    assert first.index_identity != second.index_identity


async def test_embedding_provider_passes_compatible_api_base(monkeypatch) -> None:
    captured = {}

    async def fake_embedding(**kwargs):
        captured.update(kwargs)
        return {"data": [{"embedding": [1.0, 0.0]}]}

    monkeypatch.setattr("bridle.providers.embedding_litellm.litellm.aembedding", fake_embedding)
    provider = LiteLlmEmbeddingProvider(
        embedding_config(base_url="https://embedding.example.test/v1"),
        KeyResolver({"EMBEDDING_API_KEY": "compatible-private-test"}),
    )

    await provider.embed(["project context"])

    assert captured["api_base"] == "https://embedding.example.test/v1"


def test_external_embedding_config_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL", "openai/vendor-model")
    monkeypatch.setenv("EMBEDDING_API_BASE", "https://embedding.example.test/v1")

    config = external_embedding_config()

    assert config.model == "openai/vendor-model"
    assert config.base_url == "https://embedding.example.test/v1"
    assert config.api_key_env == "EMBEDDING_API_KEY"


@pytest.mark.external_api
@pytest.mark.skipif(
    not all(
        os.environ.get(name)
        for name in ("EMBEDDING_API_KEY", "EMBEDDING_API_BASE", "EMBEDDING_MODEL")
    ),
    reason="Compatible embedding API key, base URL, and model are required.",
)
async def test_compatible_embedding_smoke() -> None:
    provider = LiteLlmEmbeddingProvider(external_embedding_config())

    vectors = await provider.embed(["Godot project context"])

    assert len(vectors) == 1
    assert vectors[0]
