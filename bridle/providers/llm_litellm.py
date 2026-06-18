from __future__ import annotations

import time
from typing import Any

import litellm

from bridle.config.key_resolver import KeyResolver
from bridle.domain.errors import AuthError, ProviderError
from bridle.domain.providers import (
    LlmChatRequest,
    LlmChatResponse,
    ProviderConfig,
    ProviderHealth,
    ProviderHealthStatus,
)


class LiteLlmProvider:
    def __init__(self, config: ProviderConfig, key_resolver: KeyResolver | None = None) -> None:
        self.config = config
        self.key_resolver = key_resolver or KeyResolver()

    async def test_connection(self) -> ProviderHealth:
        start = time.perf_counter()
        if self.config.model is None:
            return ProviderHealth(
                provider_id=self.config.provider_id,
                status=ProviderHealthStatus.CONFIG_ERROR,
                safe_details=f"Provider {self.config.provider_id!r} has no model configured.",
            )

        try:
            await self.chat(
                LlmChatRequest(
                    messages=[{"role": "user", "content": "Reply with ok."}],
                    max_tokens=4,
                )
            )
        except AuthError as error:
            return ProviderHealth(
                provider_id=self.config.provider_id,
                status=ProviderHealthStatus.MISSING_KEY,
                safe_details=error.safe_details,
            )
        except ProviderError as error:
            return ProviderHealth(
                provider_id=self.config.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                safe_details=error.safe_details,
            )

        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProviderHealth(
            provider_id=self.config.provider_id,
            status=ProviderHealthStatus.OK,
            latency_ms=latency_ms,
            safe_details=f"Connected using {self.key_resolver.describe_source(self.config)}",
        )

    async def chat(self, request: LlmChatRequest) -> LlmChatResponse:
        api_key = self.key_resolver.resolve_required(self.config)
        if self.config.model is None:
            raise ProviderError(f"Provider {self.config.provider_id!r} has no model configured.")

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": [message.model_dump() for message in request.messages],
            "api_key": api_key,
        }
        if self.config.base_url is not None:
            kwargs["api_base"] = self.config.base_url
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as error:
            message = f"LLM provider {self.config.provider_id!r} request failed."
            raise ProviderError(message) from error

        choice = response["choices"][0]
        content = choice["message"]["content"] or ""
        return LlmChatResponse(content=content, raw={"model": response.get("model", "")})
