from __future__ import annotations

from bridle.domain.capabilities import ADR_005_CAPABILITY_VALUES, ProviderCapability


def test_capability_values_match_adr_005() -> None:
    assert ADR_005_CAPABILITY_VALUES == (
        "llm.chat",
        "llm.stream",
        "llm.structured_output",
        "model3d.text_to_3d",
        "model3d.image_to_3d",
        "texture.retexture",
        "texture.pbr_generate",
        "rigging.auto_rig",
        "animation.video_to_motion",
        "animation.text_to_motion",
    )


def test_capability_values_are_unique() -> None:
    values = [capability.value for capability in ProviderCapability]

    assert len(values) == len(set(values))
