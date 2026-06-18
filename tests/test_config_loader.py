from __future__ import annotations

import pytest

from bridle.config.loader import parse_config
from bridle.domain.errors import ConfigError


def test_parse_config_rejects_plaintext_secret_fields() -> None:
    with pytest.raises(ConfigError, match="plaintext secret"):
        parse_config(
            {
                "providers": [
                    {
                        "provider_id": "deepseek",
                        "kind": "llm",
                        "api_key": "sk-plain-text",
                    }
                ]
            }
        )


def test_parse_config_accepts_api_key_env() -> None:
    config = parse_config(
        {
            "providers": [
                {
                    "provider_id": "deepseek",
                    "kind": "llm",
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "capabilities": ["llm.chat", "llm.stream"],
                    "default_for": ["llm.chat"],
                }
            ]
        }
    )

    assert config.providers[0].provider_id == "deepseek"
    assert config.providers[0].api_key_env == "DEEPSEEK_API_KEY"


def test_parse_config_warns_on_duplicate_key_source() -> None:
    config = parse_config(
        {
            "providers": [
                {
                    "provider_id": "deepseek",
                    "kind": "llm",
                    "api_key_env": "SHARED_KEY",
                },
                {
                    "provider_id": "other",
                    "kind": "llm",
                    "api_key_env": "SHARED_KEY",
                },
            ]
        }
    )

    assert len(config.warnings) == 1
    assert "SHARED_KEY" in config.warnings[0]
