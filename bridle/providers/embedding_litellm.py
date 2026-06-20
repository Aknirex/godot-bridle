from __future__ import annotations

import time
from hashlib import sha256
from typing import Any

import litellm

from bridle.config.key_resolver import KeyResolver
from bridle.domain.errors import AuthError, ProviderError
from bridle.domain.providers import ProviderConfig, ProviderHealth, ProviderHealthStatus


class LiteLlmEmbeddingProvider:
    """Production embedding provider backed by LiteLLM's compatible facade."""

    def __init__(
        self,
        config: ProviderConfig,
        key_resolver: KeyResolver | None = None,
        *,
        batch_size: int = 128,
    ) -> None:
        if batch_size < 1:
            raise ValueError("Embedding batch_size must be positive.")
        self.config = config
        self.key_resolver = key_resolver or KeyResolver()
        self.batch_size = batch_size

    @property
    def index_identity(self) -> str:
        identity = "\0".join(
            (self.config.backend or "", self.config.model or "", self.config.base_url or "")
        )
        return sha256(identity.encode()).hexdigest()[:16]

    async def test_connection(self) -> ProviderHealth:
        start = time.perf_counter()
        if self.config.model is None:
            return ProviderHealth(
                provider_id=self.config.provider_id,
                status=ProviderHealthStatus.CONFIG_ERROR,
                safe_details=f"Provider {self.config.provider_id!r} has no model configured.",
            )

        try:
            await self.embed(["connection test"])
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

        return ProviderHealth(
            provider_id=self.config.provider_id,
            status=ProviderHealthStatus.OK,
            latency_ms=int((time.perf_counter() - start) * 1000),
            safe_details=f"Connected using {self.key_resolver.describe_source(self.config)}",
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        api_key = self.key_resolver.resolve_required(self.config)
        if self.config.model is None:
            raise ProviderError(f"Provider {self.config.provider_id!r} has no model configured.")

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "input": texts,
            "api_key": api_key,
        }
        if self.config.base_url is not None:
            kwargs["api_base"] = self.config.base_url

        vectors: list[list[float]] = []
        for offset in range(0, len(texts), self.batch_size):
            kwargs["input"] = texts[offset : offset + self.batch_size]
            try:
                response = await litellm.aembedding(**kwargs)
                batch = [list(item["embedding"]) for item in response["data"]]
            except Exception as error:
                message = f"Embedding provider {self.config.provider_id!r} request failed."
                raise ProviderError(message) from error

            if len(batch) != len(kwargs["input"]) or any(not vector for vector in batch):
                raise ProviderError(
                    f"Embedding provider {self.config.provider_id!r} returned an invalid response."
                )
            vectors.extend(batch)
        return vectors
