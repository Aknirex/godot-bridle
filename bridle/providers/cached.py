from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

from bridle.domain.errors import BridleError
from bridle.domain.providers import (
    LlmChatRequest,
    LlmChatResponse,
    LlmStreamEvent,
    LlmStreamEventType,
)
from bridle.harness.cache import ExactCache, SemanticCache
from bridle.providers.base import LLMProvider


class CachedLLMProvider:
    def __init__(
        self,
        provider: LLMProvider,
        cache: ExactCache,
        *,
        semantic_cache: SemanticCache | None = None,
        ttl_seconds: float = 86_400,
    ) -> None:
        self.provider = provider
        self.config = provider.config
        self.cache = cache
        self.semantic_cache = semantic_cache
        self.ttl_seconds = ttl_seconds

    async def test_connection(self):
        return await self.provider.test_connection()

    async def close(self) -> None:
        close = getattr(self.provider, "close", None)
        if close is not None:
            await close()

    async def chat(self, request: LlmChatRequest) -> LlmChatResponse:
        key = self._key(request)
        hit = self.cache.get(key)
        if hit is not None:
            response = LlmChatResponse.model_validate(hit.value)
            response.raw["cache"] = "exact"
            return response
        semantic_hit = await self._semantic_get(request)
        if semantic_hit is not None:
            response = LlmChatResponse.model_validate(semantic_hit)
            response.raw["cache"] = "semantic"
            return response
        response = await self.provider.chat(request)
        self.cache.set(key, response.model_dump(mode="json"), ttl_seconds=self.ttl_seconds)
        await self._semantic_set(request, response)
        return response

    async def stream_chat(self, request: LlmChatRequest) -> AsyncIterator[LlmStreamEvent]:
        started = time.perf_counter()
        key = self._key(request)
        hit = self.cache.get(key)
        if hit is not None:
            response = LlmChatResponse.model_validate(hit.value)
            yield LlmStreamEvent(type=LlmStreamEventType.STARTED, model=self.config.model)
            if response.content:
                yield LlmStreamEvent(
                    type=LlmStreamEventType.DELTA,
                    delta=response.content,
                    model=self.config.model,
                    time_to_first_token_ms=0,
                )
            yield LlmStreamEvent(
                type=LlmStreamEventType.COMPLETED,
                content=response.content,
                model=self.config.model,
                latency_ms=round((time.perf_counter() - started) * 1000),
                time_to_first_token_ms=0,
            )
            return
        semantic_hit = await self._semantic_get(request)
        if semantic_hit is not None:
            response = LlmChatResponse.model_validate(semantic_hit)
            yield LlmStreamEvent(type=LlmStreamEventType.STARTED, model=self.config.model)
            if response.content:
                yield LlmStreamEvent(
                    type=LlmStreamEventType.DELTA,
                    delta=response.content,
                    model=self.config.model,
                    time_to_first_token_ms=0,
                )
            yield LlmStreamEvent(
                type=LlmStreamEventType.COMPLETED,
                content=response.content,
                model=self.config.model,
                latency_ms=round((time.perf_counter() - started) * 1000),
                time_to_first_token_ms=0,
            )
            return
        completed: LlmStreamEvent | None = None
        async for event in self.provider.stream_chat(request):
            if event.type == LlmStreamEventType.COMPLETED:
                completed = event
            yield event
        if completed is not None:
            response = LlmChatResponse(
                content=completed.content,
                raw={
                    "model": completed.model or "",
                    "usage": completed.usage.model_dump() if completed.usage else {},
                    "latency_ms": completed.latency_ms or 0,
                },
            )
            self.cache.set(
                key,
                response.model_dump(mode="json"),
                ttl_seconds=self.ttl_seconds,
            )
            await self._semantic_set(request, response)

    def _key(self, request: LlmChatRequest) -> dict:
        return {
            "kind": "llm.chat",
            "provider_id": self.config.provider_id,
            "backend": self.config.backend,
            "model": self.config.model,
            "base_url": self.config.base_url,
            "request": request.model_dump(mode="json"),
        }

    def _semantic_namespace(self, request: LlmChatRequest) -> str:
        # Parameters and model identity are part of the namespace, so a near
        # prompt cannot cross a behavior-changing configuration boundary.
        return json.dumps(
            {
                "provider_id": self.config.provider_id,
                "backend": self.config.backend,
                "model": self.config.model,
                "base_url": self.config.base_url,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _semantic_prompt(request: LlmChatRequest) -> str:
        return json.dumps(
            [message.model_dump(mode="json") for message in request.messages],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    async def _semantic_get(self, request: LlmChatRequest):
        if self.semantic_cache is None:
            return None
        try:
            hit = await self.semantic_cache.get(
                self._semantic_namespace(request), self._semantic_prompt(request)
            )
        except BridleError:
            return None
        return hit.value if hit is not None else None

    async def _semantic_set(
        self, request: LlmChatRequest, response: LlmChatResponse
    ) -> None:
        if self.semantic_cache is None:
            return
        try:
            await self.semantic_cache.set(
                self._semantic_namespace(request),
                self._semantic_prompt(request),
                response.model_dump(mode="json"),
                ttl_seconds=self.ttl_seconds,
            )
        except BridleError:
            return
