from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from bridle.domain.capabilities import ProviderCapability

NonEmptyStr = Annotated[str, Field(min_length=1)]


class ProviderKind(StrEnum):
    LLM = "llm"
    ASSET = "asset"
    GATEWAY = "gateway"


class ProviderConfig(BaseModel):
    provider_id: NonEmptyStr
    kind: ProviderKind
    backend: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    capabilities: list[ProviderCapability] = Field(default_factory=list)
    default_for: list[ProviderCapability] = Field(default_factory=list)
