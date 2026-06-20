from __future__ import annotations

from enum import StrEnum


class ProviderCapability(StrEnum):
    """Provider capabilities mirrored from docs/04-architecture-decisions.md ADR-005."""

    LLM_CHAT = "llm.chat"
    LLM_STREAM = "llm.stream"
    LLM_STRUCTURED_OUTPUT = "llm.structured_output"
    EMBEDDING_GENERATE = "embedding.generate"
    MODEL3D_TEXT_TO_3D = "model3d.text_to_3d"
    MODEL3D_IMAGE_TO_3D = "model3d.image_to_3d"
    TEXTURE_RETEXTURE = "texture.retexture"
    TEXTURE_PBR_GENERATE = "texture.pbr_generate"
    RIGGING_AUTO_RIG = "rigging.auto_rig"
    ANIMATION_VIDEO_TO_MOTION = "animation.video_to_motion"
    ANIMATION_TEXT_TO_MOTION = "animation.text_to_motion"


ADR_005_CAPABILITY_VALUES: tuple[str, ...] = tuple(
    capability.value for capability in ProviderCapability
)
