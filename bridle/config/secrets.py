from __future__ import annotations

SECRET_FIELD_NAMES = frozenset({"api_key", "secret", "token", "authorization"})
SECRET_MARKER = "***"


def mask_secret(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= 8:
        return SECRET_MARKER
    return f"{value[:4]}...{value[-4:]}"


def contains_forbidden_secret_field(data: object) -> bool:
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in SECRET_FIELD_NAMES:
                return True
            if contains_forbidden_secret_field(value):
                return True
    elif isinstance(data, list):
        return any(contains_forbidden_secret_field(item) for item in data)
    return False
