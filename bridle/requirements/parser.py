from __future__ import annotations

import json
import re
from typing import Any

from pydantic import TypeAdapter, ValidationError

from bridle.domain.production import AssetBrief

ASSET_BLOCK_PATTERN = re.compile(
    r"```(?:json\s+)?bridle-assets\s*(?P<body>.*?)```",
    re.DOTALL | re.IGNORECASE,
)
ASSET_LIST_ADAPTER = TypeAdapter(list[AssetBrief])


class RequirementParseError(ValueError):
    pass


def parse_asset_briefs(markdown: str) -> list[AssetBrief]:
    block = _extract_asset_block(markdown)
    try:
        payload = json.loads(block)
    except json.JSONDecodeError as exc:
        raise RequirementParseError(f"Invalid bridle-assets JSON: {exc.msg}") from exc

    if isinstance(payload, dict) and "assets" in payload:
        payload = payload["assets"]
    try:
        return ASSET_LIST_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise RequirementParseError(str(exc)) from exc


def _extract_asset_block(markdown: str) -> str:
    match = ASSET_BLOCK_PATTERN.search(markdown)
    if not match:
        raise RequirementParseError(
            "Missing bridle-assets fenced block. Free-form requirements must be converted "
            "to structured JSON before deterministic parsing."
        )
    return match.group("body").strip()


def fake_llm_convert_freeform_to_asset_block(markdown: str, payload: list[dict[str, Any]]) -> str:
    """Test helper that represents the LLM-assisted parser boundary.

    Production code must replace this with a real LLM/Agent conversion step. The
    deterministic parser still validates the resulting JSON schema.
    """

    del markdown
    return "```bridle-assets\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
