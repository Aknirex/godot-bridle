from __future__ import annotations

import pytest

from bridle.domain.capabilities import ProviderCapability
from bridle.domain.errors import ProviderCapabilityError
from bridle.domain.providers import ProviderConfig, ProviderKind
from bridle.providers.resolver import ProviderResolver


def provider(
    provider_id: str,
    capabilities: list[ProviderCapability],
    default_for: list[ProviderCapability] | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        kind=ProviderKind.LLM,
        capabilities=capabilities,
        default_for=default_for or [],
    )


def test_resolver_uses_explicit_provider_when_it_satisfies_capabilities() -> None:
    deepseek = provider("deepseek", [ProviderCapability.LLM_CHAT])
    other = provider("other", [ProviderCapability.LLM_CHAT], [ProviderCapability.LLM_CHAT])

    plan = ProviderResolver([deepseek, other]).resolve(
        [ProviderCapability.LLM_CHAT],
        explicit_provider_id="deepseek",
    )

    assert plan.provider_for(ProviderCapability.LLM_CHAT).provider_id == "deepseek"


def test_resolver_rejects_explicit_provider_missing_capability() -> None:
    deepseek = provider("deepseek", [ProviderCapability.LLM_CHAT])

    with pytest.raises(ProviderCapabilityError, match="does not satisfy"):
        ProviderResolver([deepseek]).resolve(
            [ProviderCapability.MODEL3D_TEXT_TO_3D],
            explicit_provider_id="deepseek",
        )


def test_resolver_prefers_default_for_then_declaration_order() -> None:
    first = provider("first", [ProviderCapability.LLM_CHAT])
    second = provider("second", [ProviderCapability.LLM_CHAT], [ProviderCapability.LLM_CHAT])

    plan = ProviderResolver([first, second]).resolve([ProviderCapability.LLM_CHAT])

    assert plan.provider_for(ProviderCapability.LLM_CHAT).provider_id == "second"


def test_resolver_uses_declaration_order_without_default() -> None:
    first = provider("first", [ProviderCapability.LLM_CHAT])
    second = provider("second", [ProviderCapability.LLM_CHAT])

    plan = ProviderResolver([first, second]).resolve([ProviderCapability.LLM_CHAT])

    assert plan.provider_for(ProviderCapability.LLM_CHAT).provider_id == "first"


def test_resolver_can_make_multi_provider_plan() -> None:
    llm = provider("deepseek", [ProviderCapability.LLM_CHAT])
    asset = provider("meshy", [ProviderCapability.MODEL3D_TEXT_TO_3D])

    plan = ProviderResolver([llm, asset]).resolve(
        [ProviderCapability.LLM_CHAT, ProviderCapability.MODEL3D_TEXT_TO_3D]
    )

    assert plan.provider_for(ProviderCapability.LLM_CHAT).provider_id == "deepseek"
    assert plan.provider_for(ProviderCapability.MODEL3D_TEXT_TO_3D).provider_id == "meshy"
