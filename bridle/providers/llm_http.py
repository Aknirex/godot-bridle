from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from hashlib import sha256
from typing import Any

import httpx

from bridle.config.key_resolver import KeyResolver
from bridle.domain.errors import AuthError, ProviderError
from bridle.domain.providers import (
    LlmChatRequest,
    LlmChatResponse,
    LlmStreamEvent,
    LlmStreamEventType,
    LlmUsage,
    ProviderConfig,
    ProviderHealth,
    ProviderHealthStatus,
)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"


class OpenAICompatibleProvider:
    """Small OpenAI-compatible adapter without importing a provider mega-SDK."""

    def __init__(
        self,
        config: ProviderConfig,
        key_resolver: KeyResolver | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.key_resolver = key_resolver or KeyResolver()
        self._client = client
        self._owned_client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    async def test_connection(self) -> ProviderHealth:
        return await _test_chat_connection(self)

    async def chat(self, request: LlmChatRequest) -> LlmChatResponse:
        started = time.perf_counter()
        payload = self._payload(request, stream=False)
        response = await self._request("POST", "/chat/completions", json=payload)
        try:
            choice = response["choices"][0]
            content = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("LLM provider returned an invalid chat response.") from error
        raw = {
            "model": str(response.get("model") or self.config.model or ""),
            "usage": _json_object(response.get("usage")),
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }
        return LlmChatResponse(content=str(content), raw=raw)

    async def stream_chat(self, request: LlmChatRequest) -> AsyncIterator[LlmStreamEvent]:
        started = time.perf_counter()
        first_token_ms: int | None = None
        content_parts: list[str] = []
        finish_reason: str | None = None
        usage: LlmUsage | None = None
        model = self.config.model
        yield LlmStreamEvent(type=LlmStreamEventType.STARTED, model=model)
        client = self._ensure_client()
        url = f"{self._base_url()}/chat/completions"
        try:
            async with client.stream(
                "POST",
                url,
                headers=self._headers(),
                json=self._payload(request, stream=True),
            ) as response:
                await _raise_for_status(response, "LLM")
                async for data in _iter_sse_data(response):
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError as error:
                        raise ProviderError("LLM provider returned malformed SSE data.") from error
                    model = str(event.get("model") or model or "") or None
                    raw_usage = event.get("usage")
                    if isinstance(raw_usage, dict):
                        usage = LlmUsage(
                            input_tokens=_optional_int(raw_usage.get("prompt_tokens")),
                            output_tokens=_optional_int(raw_usage.get("completion_tokens")),
                        )
                    for choice in event.get("choices") or []:
                        if not isinstance(choice, dict):
                            continue
                        finish_reason = choice.get("finish_reason") or finish_reason
                        delta = choice.get("delta") or {}
                        text = delta.get("content") if isinstance(delta, dict) else None
                        if not isinstance(text, str) or not text:
                            continue
                        if first_token_ms is None:
                            first_token_ms = round((time.perf_counter() - started) * 1000)
                        content_parts.append(text)
                        yield LlmStreamEvent(
                            type=LlmStreamEventType.DELTA,
                            delta=text,
                            model=model,
                            time_to_first_token_ms=first_token_ms,
                        )
        except httpx.HTTPError as error:
            raise ProviderError("LLM provider streaming request failed.") from error
        yield LlmStreamEvent(
            type=LlmStreamEventType.COMPLETED,
            content="".join(content_parts),
            model=model,
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=round((time.perf_counter() - started) * 1000),
            time_to_first_token_ms=first_token_ms,
        )

    def _payload(self, request: LlmChatRequest, *, stream: bool) -> dict[str, Any]:
        if self.config.model is None:
            raise ProviderError(f"Provider {self.config.provider_id!r} has no model configured.")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [message.model_dump() for message in request.messages],
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        return payload

    async def _request(
        self, method: str, path: str, *, json: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            response = await self._ensure_client().request(
                method,
                f"{self._base_url()}{path}",
                headers=self._headers(),
                json=json,
            )
            await _raise_for_status(response, "LLM")
            data = response.json()
        except httpx.HTTPError as error:
            raise ProviderError("LLM provider request failed.") from error
        except ValueError as error:
            raise ProviderError("LLM provider returned invalid JSON.") from error
        if not isinstance(data, dict):
            raise ProviderError("LLM provider response was not a JSON object.")
        return data

    def _base_url(self) -> str:
        return (self.config.base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")

    def _headers(self) -> dict[str, str]:
        api_key = self.key_resolver.resolve_required(self.config)
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))
        return self._owned_client


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        config: ProviderConfig,
        key_resolver: KeyResolver | None = None,
        client: httpx.AsyncClient | None = None,
        *,
        batch_size: int = 128,
    ) -> None:
        if batch_size < 1:
            raise ValueError("Embedding batch_size must be positive.")
        self.config = config
        self.key_resolver = key_resolver or KeyResolver()
        self._client = client
        self._owned_client: httpx.AsyncClient | None = None
        self.batch_size = batch_size

    @property
    def index_identity(self) -> str:
        value = "\0".join(
            (self.config.backend or "", self.config.model or "", self.config.base_url or "")
        )
        return sha256(value.encode()).hexdigest()[:16]

    async def close(self) -> None:
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    async def test_connection(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            await self.embed(["connection test"])
        except AuthError as error:
            return _health_error(self.config, ProviderHealthStatus.MISSING_KEY, error)
        except ProviderError as error:
            return _health_error(self.config, ProviderHealthStatus.UNAVAILABLE, error)
        return ProviderHealth(
            provider_id=self.config.provider_id,
            status=ProviderHealthStatus.OK,
            latency_ms=round((time.perf_counter() - started) * 1000),
            safe_details=f"Connected using {self.key_resolver.describe_source(self.config)}",
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.config.model is None:
            raise ProviderError(f"Provider {self.config.provider_id!r} has no model configured.")
        api_key = self.key_resolver.resolve_required(self.config)
        base_url = (self.config.base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")
        client = self._ensure_client()
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), self.batch_size):
            batch = texts[offset : offset + self.batch_size]
            try:
                response = await client.post(
                    f"{base_url}/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": self.config.model, "input": batch},
                )
                await _raise_for_status(response, "Embedding")
                data = response.json()
                items = data.get("data") if isinstance(data, dict) else None
                parsed = [list(item["embedding"]) for item in items or []]
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                raise ProviderError("Embedding provider request failed.") from error
            if len(parsed) != len(batch) or any(not vector for vector in parsed):
                raise ProviderError("Embedding provider returned an invalid response.")
            vectors.extend(parsed)
        return vectors

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))
        return self._owned_client


class AnthropicProvider:
    def __init__(
        self,
        config: ProviderConfig,
        key_resolver: KeyResolver | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.key_resolver = key_resolver or KeyResolver()
        self._client = client
        self._owned_client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    async def test_connection(self) -> ProviderHealth:
        return await _test_chat_connection(self)

    async def chat(self, request: LlmChatRequest) -> LlmChatResponse:
        started = time.perf_counter()
        response = await self._ensure_client().post(
            f"{self._base_url()}/messages",
            headers=self._headers(),
            json=self._payload(request, stream=False),
        )
        await _raise_for_status(response, "Anthropic")
        try:
            data = response.json()
            content = "".join(
                str(block.get("text", ""))
                for block in data.get("content", [])
                if isinstance(block, dict) and block.get("type") == "text"
            )
        except (TypeError, ValueError) as error:
            raise ProviderError("Anthropic returned an invalid chat response.") from error
        return LlmChatResponse(
            content=content,
            raw={
                "model": str(data.get("model") or self.config.model or ""),
                "usage": _json_object(data.get("usage")),
                "latency_ms": round((time.perf_counter() - started) * 1000),
            },
        )

    async def stream_chat(self, request: LlmChatRequest) -> AsyncIterator[LlmStreamEvent]:
        started = time.perf_counter()
        first_token_ms: int | None = None
        content_parts: list[str] = []
        finish_reason: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        yield LlmStreamEvent(type=LlmStreamEventType.STARTED, model=self.config.model)
        try:
            async with self._ensure_client().stream(
                "POST",
                f"{self._base_url()}/messages",
                headers=self._headers(),
                json=self._payload(request, stream=True),
            ) as response:
                await _raise_for_status(response, "Anthropic")
                async for data in _iter_sse_data(response):
                    event = json.loads(data)
                    event_type = event.get("type")
                    if event_type == "message_start":
                        input_tokens = _optional_int(
                            (event.get("message") or {}).get("usage", {}).get("input_tokens")
                        )
                    elif event_type == "content_block_delta":
                        delta = event.get("delta") or {}
                        text = delta.get("text") if delta.get("type") == "text_delta" else None
                        if isinstance(text, str) and text:
                            if first_token_ms is None:
                                first_token_ms = round(
                                    (time.perf_counter() - started) * 1000
                                )
                            content_parts.append(text)
                            yield LlmStreamEvent(
                                type=LlmStreamEventType.DELTA,
                                delta=text,
                                model=self.config.model,
                                time_to_first_token_ms=first_token_ms,
                            )
                    elif event_type == "message_delta":
                        finish_reason = (event.get("delta") or {}).get("stop_reason")
                        output_tokens = _optional_int(
                            (event.get("usage") or {}).get("output_tokens")
                        )
        except (httpx.HTTPError, json.JSONDecodeError) as error:
            raise ProviderError("Anthropic streaming request failed.") from error
        yield LlmStreamEvent(
            type=LlmStreamEventType.COMPLETED,
            content="".join(content_parts),
            model=self.config.model,
            finish_reason=finish_reason,
            usage=LlmUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            latency_ms=round((time.perf_counter() - started) * 1000),
            time_to_first_token_ms=first_token_ms,
        )

    def _payload(self, request: LlmChatRequest, *, stream: bool) -> dict[str, Any]:
        if self.config.model is None:
            raise ProviderError(f"Provider {self.config.provider_id!r} has no model configured.")
        system_parts = [m.content for m in request.messages if m.role == "system"]
        messages = [m.model_dump() for m in request.messages if m.role != "system"]
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 1024,
            "stream": stream,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        return payload

    def _base_url(self) -> str:
        return (self.config.base_url or DEFAULT_ANTHROPIC_BASE_URL).rstrip("/")

    def _headers(self) -> dict[str, str]:
        api_key = self.key_resolver.resolve_required(self.config)
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))
        return self._owned_client


async def _test_chat_connection(provider: Any) -> ProviderHealth:
    started = time.perf_counter()
    try:
        await provider.chat(
            LlmChatRequest(
                messages=[{"role": "user", "content": "Reply with ok."}],
                max_tokens=4,
            )
        )
    except AuthError as error:
        return _health_error(provider.config, ProviderHealthStatus.MISSING_KEY, error)
    except ProviderError as error:
        return _health_error(provider.config, ProviderHealthStatus.UNAVAILABLE, error)
    return ProviderHealth(
        provider_id=provider.config.provider_id,
        status=ProviderHealthStatus.OK,
        latency_ms=round((time.perf_counter() - started) * 1000),
        safe_details=f"Connected using {provider.key_resolver.describe_source(provider.config)}",
    )


async def _iter_sse_data(response: httpx.Response) -> AsyncIterator[str]:
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines.clear()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield "\n".join(data_lines)


async def _raise_for_status(response: httpx.Response, label: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        if status in {401, 403}:
            raise AuthError(f"{label} authentication failed.") from error
        raise ProviderError(f"{label} request failed with HTTP {status}.") from error


def _health_error(
    config: ProviderConfig, status: ProviderHealthStatus, error: Exception
) -> ProviderHealth:
    details = error.safe_details if isinstance(error, (AuthError, ProviderError)) else str(error)
    return ProviderHealth(
        provider_id=config.provider_id,
        status=status,
        safe_details=details,
    )


def _json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) else None

