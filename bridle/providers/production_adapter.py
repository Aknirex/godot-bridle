from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from bridle.domain.capabilities import ProviderCapability
from bridle.domain.production import AssetKind, AssetProductionRequest
from bridle.domain.providers import AssetGenerationRequest, ProviderConfig
from bridle.providers.resolver import ProviderPlan, ProviderResolver


class AssetProductionPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    production_request: AssetProductionRequest
    provider_plan: ProviderPlan
    asset_provider: ProviderConfig
    generation_request: AssetGenerationRequest


def required_capabilities_for_request(
    request: AssetProductionRequest,
) -> list[ProviderCapability]:
    if request.required_capabilities:
        return request.required_capabilities
    if request.asset.kind == AssetKind.MODEL_3D:
        return [ProviderCapability.MODEL3D_TEXT_TO_3D]
    if request.asset.kind == AssetKind.TEXTURE:
        return [ProviderCapability.TEXTURE_RETEXTURE]
    if request.asset.kind == AssetKind.RIGGING:
        return [ProviderCapability.RIGGING_AUTO_RIG]
    if request.asset.kind == AssetKind.ANIMATION:
        return [ProviderCapability.ANIMATION_TEXT_TO_MOTION]
    raise ValueError(f"Unsupported asset kind: {request.asset.kind}")


def to_asset_generation_request(
    request: AssetProductionRequest,
) -> AssetGenerationRequest:
    options = dict(request.provider_options)
    options.update(
        {
            "asset_id": request.asset.asset_id,
            "asset_title": request.asset.title,
            "purpose": request.asset.purpose,
            "target_res_path": request.asset.target_res_path,
            "acceptance": request.asset.acceptance.model_dump(mode="json"),
        }
    )
    return AssetGenerationRequest(
        prompt=request.prompt,
        output_format=request.output_format,
        provider_options=options,
    )


def plan_asset_production(
    request: AssetProductionRequest,
    resolver: ProviderResolver,
    *,
    explicit_provider_id: str | None = None,
) -> AssetProductionPlan:
    required = required_capabilities_for_request(request)
    provider_plan = resolver.resolve(required, explicit_provider_id=explicit_provider_id)
    primary_capability = required[0]
    return AssetProductionPlan(
        production_request=request,
        provider_plan=provider_plan,
        asset_provider=provider_plan.provider_for(primary_capability),
        generation_request=to_asset_generation_request(request),
    )
