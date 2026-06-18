from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from bridle.domain.capabilities import ProviderCapability
from bridle.domain.errors import ProviderCapabilityError
from bridle.domain.providers import ProviderConfig


@dataclass(frozen=True)
class ProviderPlan:
    providers: dict[ProviderCapability, ProviderConfig]

    def provider_for(self, capability: ProviderCapability) -> ProviderConfig:
        return self.providers[capability]


class ProviderResolver:
    def __init__(self, providers: Iterable[ProviderConfig]) -> None:
        self._providers = list(providers)

    def resolve(
        self,
        required_capabilities: Iterable[ProviderCapability],
        explicit_provider_id: str | None = None,
    ) -> ProviderPlan:
        required = list(required_capabilities)
        if not required:
            raise ProviderCapabilityError("At least one provider capability is required.")

        if explicit_provider_id is not None:
            provider = self._find_by_id(explicit_provider_id)
            missing = [
                capability for capability in required if capability not in provider.capabilities
            ]
            if missing:
                missing_values = ", ".join(capability.value for capability in missing)
                raise ProviderCapabilityError(
                    f"Provider {explicit_provider_id!r} does not satisfy: {missing_values}"
                )
            return ProviderPlan({capability: provider for capability in required})

        return ProviderPlan(
            {capability: self._resolve_capability(capability) for capability in required}
        )

    def _find_by_id(self, provider_id: str) -> ProviderConfig:
        for provider in self._providers:
            if provider.provider_id == provider_id:
                return provider
        raise ProviderCapabilityError(f"Provider {provider_id!r} is not configured.")

    def _resolve_capability(self, capability: ProviderCapability) -> ProviderConfig:
        candidates = [
            provider for provider in self._providers if capability in provider.capabilities
        ]
        if not candidates:
            raise ProviderCapabilityError(f"No provider satisfies capability {capability.value!r}.")

        defaults = [provider for provider in candidates if capability in provider.default_for]
        if defaults:
            return defaults[0]
        return candidates[0]
