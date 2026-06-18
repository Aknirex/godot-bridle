from __future__ import annotations

from bridle.config.secrets import contains_forbidden_secret_field, mask_secret


def test_detects_forbidden_secret_fields_recursively() -> None:
    assert contains_forbidden_secret_field({"providers": [{"api_key": "plain-text"}]})
    assert contains_forbidden_secret_field({"auth": {"token": "plain-text"}})


def test_allows_api_key_env_reference() -> None:
    assert not contains_forbidden_secret_field({"api_key_env": "DEEPSEEK_API_KEY"})


def test_masks_secret_values() -> None:
    assert mask_secret("sk-1234567890abcdef") == "sk-1...cdef"
    assert mask_secret("short") == "***"
    assert mask_secret(None) is None
