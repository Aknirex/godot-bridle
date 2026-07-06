from __future__ import annotations

from pathlib import Path

import pytest

from bridle.domain.capabilities import ProviderCapability
from bridle.domain.errors import ProviderCapabilityError
from bridle.domain.production import AssetBrief, AssetKind, AssetProductionRequest
from bridle.domain.providers import ProviderConfig, ProviderKind
from bridle.providers.production_adapter import (
    plan_asset_production,
    to_asset_generation_request,
)
from bridle.providers.resolver import ProviderResolver
from bridle.requirements.parser import (
    RequirementParseError,
    fake_llm_convert_freeform_to_asset_block,
    parse_asset_briefs,
)

FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def asset_provider(provider_id: str = "meshy_mock") -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        kind=ProviderKind.ASSET,
        capabilities=[ProviderCapability.MODEL3D_TEXT_TO_3D],
        default_for=[ProviderCapability.MODEL3D_TEXT_TO_3D],
    )


def production_request() -> AssetProductionRequest:
    brief = parse_asset_briefs((FIXTURES / "low_poly_pack.md").read_text(encoding="utf-8"))[0]
    return AssetProductionRequest(
        request_id="request_hero_knight",
        source_document="low_poly_pack.md",
        asset=brief,
        prompt=(
            "Create a low-poly fantasy knight hero with helmet, sword, and simple armor. "
            "Avoid photorealism and gore."
        ),
    )


def test_parse_structured_bridle_assets_block() -> None:
    briefs = parse_asset_briefs((FIXTURES / "low_poly_pack.md").read_text(encoding="utf-8"))

    assert len(briefs) == 1
    assert briefs[0].asset_id == "hero_knight"
    assert briefs[0].acceptance.required_format == "glb"
    assert briefs[0].acceptance.must_include == ["helmet", "sword", "simple armor"]


def test_freeform_requires_llm_or_agent_conversion_boundary() -> None:
    with pytest.raises(RequirementParseError, match="Missing bridle-assets"):
        parse_asset_briefs("Make a low-poly knight with a sword for a prototype.")


def test_fake_llm_conversion_still_uses_deterministic_validation() -> None:
    structured = fake_llm_convert_freeform_to_asset_block(
        "Make a low-poly sword prop.",
        [
            {
                "asset_id": "iron_sword",
                "kind": "model_3d",
                "title": "Iron sword prop",
                "purpose": "Handheld weapon prop for the knight.",
                "description": "A simple low-poly iron sword.",
                "style_tags": ["low-poly"],
                "target_res_path": "res://bridle/generated/iron_sword/source/asset.glb",
                "priority": 2,
                "acceptance": {
                    "target_res_path": "res://bridle/generated/iron_sword/source/asset.glb",
                    "must_include": ["sword"],
                },
            }
        ],
    )

    assert parse_asset_briefs(structured)[0].asset_id == "iron_sword"


def test_acceptance_target_path_must_match_asset_target() -> None:
    payload = """
```bridle-assets
[
  {
    "asset_id": "bad",
    "title": "Bad asset",
    "purpose": "Test validation.",
    "description": "Invalid paths.",
    "target_res_path": "res://bridle/generated/bad/source/asset.glb",
    "acceptance": {
      "target_res_path": "res://other/path.glb"
    }
  }
]
```
"""

    with pytest.raises(RequirementParseError, match="acceptance.target_res_path"):
        parse_asset_briefs(payload)


def test_production_request_adapts_to_existing_asset_generation_request() -> None:
    generation_request = to_asset_generation_request(production_request())

    assert generation_request.output_format == "glb"
    assert "low-poly fantasy knight" in generation_request.prompt
    assert generation_request.provider_options["asset_id"] == "hero_knight"
    assert generation_request.provider_options["acceptance"]["max_provider_attempts"] == 2


def test_asset_production_planning_reuses_provider_resolver() -> None:
    request = production_request()
    resolver = ProviderResolver([asset_provider()])

    plan = plan_asset_production(request, resolver)

    assert plan.asset_provider.provider_id == "meshy_mock"
    assert (
        plan.provider_plan.provider_for(ProviderCapability.MODEL3D_TEXT_TO_3D).provider_id
        == "meshy_mock"
    )
    assert plan.generation_request.provider_options["target_res_path"].startswith("res://")


def test_asset_production_planning_surfaces_resolver_errors() -> None:
    request = production_request()
    resolver = ProviderResolver(
        [
            ProviderConfig(
                provider_id="chat_only",
                kind=ProviderKind.LLM,
                capabilities=[ProviderCapability.LLM_CHAT],
            )
        ]
    )

    with pytest.raises(ProviderCapabilityError, match="model3d.text_to_3d"):
        plan_asset_production(request, resolver)


def test_default_capability_is_derived_from_asset_kind() -> None:
    request = AssetProductionRequest(
        request_id="request_texture",
        asset=AssetBrief(
            asset_id="hero_retexture",
            kind=AssetKind.TEXTURE,
            title="Hero armor retexture",
            purpose="Create a darker armor material variant.",
            description="A hand-painted darker metal texture pass for the hero armor.",
            target_res_path="res://bridle/generated/hero_retexture/source/asset.glb",
            acceptance={
                "target_res_path": "res://bridle/generated/hero_retexture/source/asset.glb"
            },
        ),
        prompt="Create a dark hand-painted armor texture variant.",
    )

    assert request.required_capabilities == [ProviderCapability.TEXTURE_RETEXTURE]
