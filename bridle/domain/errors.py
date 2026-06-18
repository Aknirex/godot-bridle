from __future__ import annotations

from enum import StrEnum


class BridleErrorCode(StrEnum):
    CONFIG_ERROR = "config_error"
    AUTH_ERROR = "auth_error"
    PROVIDER_CAPABILITY_ERROR = "provider_capability_error"
    PROVIDER_ERROR = "provider_error"
    JOB_NOT_FOUND = "job_not_found"
    JOB_CANCELLED = "job_cancelled"
    INTERNAL_ERROR = "internal_error"


class BridleError(Exception):
    def __init__(self, code: BridleErrorCode, safe_details: str) -> None:
        super().__init__(safe_details)
        self.code = code
        self.safe_details = safe_details


class ConfigError(BridleError):
    def __init__(self, safe_details: str) -> None:
        super().__init__(BridleErrorCode.CONFIG_ERROR, safe_details)


class AuthError(BridleError):
    def __init__(self, safe_details: str) -> None:
        super().__init__(BridleErrorCode.AUTH_ERROR, safe_details)


class ProviderError(BridleError):
    def __init__(self, safe_details: str) -> None:
        super().__init__(BridleErrorCode.PROVIDER_ERROR, safe_details)


class ProviderCapabilityError(BridleError):
    def __init__(self, safe_details: str) -> None:
        super().__init__(BridleErrorCode.PROVIDER_CAPABILITY_ERROR, safe_details)


class JobNotFoundError(BridleError):
    def __init__(self, job_id: str) -> None:
        super().__init__(BridleErrorCode.JOB_NOT_FOUND, f"Job not found: {job_id}")
