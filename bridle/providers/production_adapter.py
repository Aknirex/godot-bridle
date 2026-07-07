from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from bridle.domain.production import AssetProductionRequest
from bridle.domain.providers import AssetGenerationRequest, ProviderConfig
from bridle.providers.resolver import ProviderPlan, ProviderResolver


class AssetProductionPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    production_request: AssetProductionRequest
    provider_plan: ProviderPlan
    asset_provider: ProviderConfig
    generation_request: AssetGenerationRequest


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
    required = request.required_capabilities
    provider_plan = resolver.resolve(required, explicit_provider_id=explicit_provider_id)
    primary_capability = required[0]
    return AssetProductionPlan(
        production_request=request,
        provider_plan=provider_plan,
        asset_provider=provider_plan.provider_for(primary_capability),
        generation_request=to_asset_generation_request(request),
    )
