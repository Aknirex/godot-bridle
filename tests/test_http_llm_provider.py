from __future__ import annotations

import httpx

from bridle.config.key_resolver import KeyResolver
from bridle.domain.providers import LlmChatRequest, ProviderConfig, ProviderKind
from bridle.providers.llm_http import (
    AnthropicProvider,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleProvider,
)


def _config(backend: str = "openai_compatible") -> ProviderConfig:
    return ProviderConfig(
        provider_id="test",
        kind=ProviderKind.LLM,
        backend=backend,
        model="test-model",
        base_url="https://provider.test/v1",
        api_key_env="TEST_API_KEY",
    )


async def test_openai_compatible_chat_and_stream() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        body = request.content.decode()
        if '"stream":true' in body:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=(
                    'data: {"model":"test-model","choices":[{"delta":{"content":"hel"}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n'
                    'data: {"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":1}}\n\n'
                    "data: [DONE]\n\n"
                ),
            )
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        _config(), KeyResolver({"TEST_API_KEY": "secret"}), client
    )
    request = LlmChatRequest(messages=[{"role": "user", "content": "hi"}])

    response = await provider.chat(request)
    events = [event async for event in provider.stream_chat(request)]

    assert response.content == "hello"
    assert [event.type for event in events] == ["started", "delta", "delta", "completed"]
    assert events[-1].content == "hello"
    assert events[-1].usage is not None
    assert events[-1].usage.input_tokens == 2
    await client.aclose()


async def test_openai_compatible_embeddings() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"embedding": [1.0, 0.0]}, {"embedding": [0.0, 1.0]}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleEmbeddingProvider(
        _config(), KeyResolver({"TEST_API_KEY": "secret"}), client
    )

    assert await provider.embed(["one", "two"]) == [[1.0, 0.0], [0.0, 1.0]]
    await client.aclose()


async def test_anthropic_chat_and_stream() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "secret"
        if b'"stream":true' in request.content:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=(
                    'data: {"type":"message_start","message":{"usage":{"input_tokens":3}}}\n\n'
                    'data: {"type":"content_block_delta","delta":'
                    '{"type":"text_delta","text":"ok"}}\n\n'
                    'data: {"type":"message_delta","delta":'
                    '{"stop_reason":"end_turn"},"usage":{"output_tokens":1}}\n\n'
                ),
            )
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 3, "output_tokens": 1},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AnthropicProvider(
        _config("anthropic"), KeyResolver({"TEST_API_KEY": "secret"}), client
    )
    request = LlmChatRequest(
        messages=[
            {"role": "system", "content": "Be brief"},
            {"role": "user", "content": "reply"},
        ]
    )

    assert (await provider.chat(request)).content == "ok"
    events = [event async for event in provider.stream_chat(request)]
    assert events[-1].content == "ok"
    assert events[-1].finish_reason == "end_turn"
    await client.aclose()
