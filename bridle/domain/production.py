from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bridle.domain.capabilities import ProviderCapability
from bridle.domain.events import JsonValue

NonEmptyStr = Annotated[str, Field(min_length=1)]


class AssetKind(StrEnum):
    MODEL_3D = "model_3d"
    TEXTURE = "texture"
    RIGGING = "rigging"
    ANIMATION = "animation"


class AssetAcceptanceCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_format: NonEmptyStr = "glb"
    godot_import_required: bool = True
    target_res_path: NonEmptyStr
    scale_hint: str | None = None
    style_tags: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    max_provider_attempts: int = Field(default=1, ge=1, le=5)
    manual_review_required: bool = True


class AssetBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: NonEmptyStr
    kind: AssetKind = AssetKind.MODEL_3D
    title: NonEmptyStr
    purpose: NonEmptyStr
    description: NonEmptyStr
    style_tags: list[str] = Field(default_factory=list)
    target_res_path: NonEmptyStr
    priority: int = Field(default=3, ge=1, le=5)
    dependencies: list[str] = Field(default_factory=list)
    constraints: dict[str, JsonValue] = Field(default_factory=dict)
    acceptance: AssetAcceptanceCriteria

    @field_validator("acceptance")
    @classmethod
    def target_path_must_match_acceptance(
        cls, acceptance: AssetAcceptanceCriteria, info
    ) -> AssetAcceptanceCriteria:
        data = info.data
        target_res_path = data.get("target_res_path")
        if target_res_path and acceptance.target_res_path != target_res_path:
            raise ValueError("acceptance.target_res_path must match target_res_path")
        return acceptance


class AssetProductionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyStr
    source_document: str | None = None
    asset: AssetBrief
    prompt: NonEmptyStr
    required_capabilities: list[ProviderCapability] = Field(default_factory=list)
    output_format: NonEmptyStr = "glb"
    provider_options: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_default_capabilities(self) -> AssetProductionRequest:
        if self.required_capabilities:
            return self
        defaults = {
            AssetKind.MODEL_3D: ProviderCapability.MODEL3D_TEXT_TO_3D,
            AssetKind.TEXTURE: ProviderCapability.TEXTURE_RETEXTURE,
            AssetKind.RIGGING: ProviderCapability.RIGGING_AUTO_RIG,
            AssetKind.ANIMATION: ProviderCapability.ANIMATION_TEXT_TO_MOTION,
        }
        self.required_capabilities = [defaults[self.asset.kind]]
        return self
