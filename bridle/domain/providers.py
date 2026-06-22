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


class LlmStreamEventType(StrEnum):
    STARTED = "started"
    DELTA = "delta"
    COMPLETED = "completed"


class LlmUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmStreamEvent(BaseModel):
    type: LlmStreamEventType
    delta: str = ""
    content: str = ""
    model: str | None = None
    finish_reason: str | None = None
    usage: LlmUsage | None = None
    latency_ms: int | None = None
    time_to_first_token_ms: int | None = None


class AssetTaskStatus(StrEnum):
    SUBMITTED = "submitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class AssetGenerationRequest(BaseModel):
    prompt: str = ""
    image_url: str | None = None
    source_task_id: str | None = None
    model_url: str | None = None
    output_format: str = "glb"
    provider_options: dict[str, JsonValue] = Field(default_factory=dict)


class AssetTaskRef(BaseModel):
    provider_id: str
    task_id: str
    status: AssetTaskStatus = AssetTaskStatus.SUBMITTED
    task_type: str = "text_to_3d"
    poll_path: str | None = None
    raw: dict[str, JsonValue] = Field(default_factory=dict)


class AssetTaskResult(BaseModel):
    provider_id: str
    task_id: str
    status: AssetTaskStatus
    task_type: str = "text_to_3d"
    progress: float | None = None
    asset_urls: list[str] = Field(default_factory=list)
    texture_urls: dict[str, str] = Field(default_factory=dict)
    raw: dict[str, JsonValue] = Field(default_factory=dict)
