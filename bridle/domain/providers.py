from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from bridle.domain.capabilities import ProviderCapability
from bridle.domain.events import JsonValue

NonEmptyStr = Annotated[str, Field(min_length=1)]


class ProviderKind(StrEnum):
    LLM = "llm"
    ASSET = "asset"
    GATEWAY = "gateway"


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: NonEmptyStr
    kind: ProviderKind
    backend: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    capabilities: list[ProviderCapability] = Field(default_factory=list)
    default_for: list[ProviderCapability] = Field(default_factory=list)


class ProviderHealthStatus(StrEnum):
    OK = "ok"
    CONFIG_ERROR = "config_error"
    MISSING_KEY = "missing_key"
    AUTH_FAILED = "auth_failed"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ProviderHealth(BaseModel):
    provider_id: str
    status: ProviderHealthStatus
    latency_ms: int | None = None
    safe_details: str = ""


class ChatMessage(BaseModel):
    role: str
    content: str


class LlmChatRequest(BaseModel):
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None


class LlmChatResponse(BaseModel):
    content: str
    raw: dict[str, JsonValue] = Field(default_factory=dict)


class AssetTaskStatus(StrEnum):
    SUBMITTED = "submitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class AssetGenerationRequest(BaseModel):
    prompt: str
    output_format: str = "glb"
    provider_options: dict[str, JsonValue] = Field(default_factory=dict)


class AssetTaskRef(BaseModel):
    provider_id: str
    task_id: str
    status: AssetTaskStatus = AssetTaskStatus.SUBMITTED
    raw: dict[str, JsonValue] = Field(default_factory=dict)


class AssetTaskResult(BaseModel):
    provider_id: str
    task_id: str
    status: AssetTaskStatus
    asset_urls: list[str] = Field(default_factory=list)
    raw: dict[str, JsonValue] = Field(default_factory=dict)
