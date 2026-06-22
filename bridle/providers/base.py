from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from bridle.domain.providers import (
    AssetGenerationRequest,
    AssetTaskRef,
    AssetTaskResult,
    LlmChatRequest,
    LlmChatResponse,
    LlmStreamEvent,
    ProviderConfig,
    ProviderHealth,
)


@runtime_checkable
class LLMProvider(Protocol):
    config: ProviderConfig

    async def test_connection(self) -> ProviderHealth: ...

    async def chat(self, request: LlmChatRequest) -> LlmChatResponse: ...

    def stream_chat(self, request: LlmChatRequest) -> AsyncIterator[LlmStreamEvent]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    config: ProviderConfig

    @property
    def index_identity(self) -> str: ...

    async def test_connection(self) -> ProviderHealth: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class AssetProvider(Protocol):
    config: ProviderConfig

    async def test_connection(self) -> ProviderHealth: ...

    async def submit_text_to_3d(self, request: AssetGenerationRequest) -> AssetTaskRef: ...

    async def submit_image_to_3d(self, request: AssetGenerationRequest) -> AssetTaskRef: ...

    async def submit_refine(
        self,
        preview_task_id: str,
        request: AssetGenerationRequest | None = None,
    ) -> AssetTaskRef: ...

    async def submit_retexture(self, request: AssetGenerationRequest) -> AssetTaskRef: ...

    async def submit_auto_rig(self, request: AssetGenerationRequest) -> AssetTaskRef: ...

    async def poll_task(self, task: AssetTaskRef | str) -> AssetTaskResult: ...

    async def cancel_task(self, task: AssetTaskRef | str) -> None: ...
