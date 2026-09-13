"""Provider-boundary errors shared by every adapter implementation."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

from arbiscan.domain import ProviderId


class ProviderErrorKind(StrEnum):
    """Stable failure categories that may cross the provider boundary."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    INVALID_REQUEST = "invalid_request"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    UPSTREAM = "upstream"
    MALFORMED_RESPONSE = "malformed_response"
    UNSUPPORTED = "unsupported"
    INTERNAL = "internal"


class ProviderContractError(ValueError):
    """Raised when provider contract data or configuration is structurally invalid."""


class ProviderError(RuntimeError):
    """Generic structured adapter failure that prevents provider-specific leakage."""

    def __init__(
        self,
        *,
        provider_id: ProviderId,
        operation: str,
        kind: ProviderErrorKind,
        message: str,
        retryable: bool = False,
        retry_after: timedelta | None = None,
    ) -> None:
        if not isinstance(provider_id, ProviderId):
            raise ProviderContractError("provider error provider_id must be ProviderId")
        if not isinstance(operation, str) or not operation.strip():
            raise ProviderContractError("provider error operation must be non-empty text")
        if not isinstance(kind, ProviderErrorKind):
            raise ProviderContractError("provider error kind must be ProviderErrorKind")
        if not isinstance(message, str) or not message.strip():
            raise ProviderContractError("provider error message must be non-empty text")
        if type(retryable) is not bool:
            raise ProviderContractError("provider error retryable must be bool")
        if retry_after is not None:
            if not isinstance(retry_after, timedelta):
                raise ProviderContractError("provider error retry_after must be timedelta")
            if retry_after.total_seconds() < 0:
                raise ProviderContractError("provider error retry_after cannot be negative")

        self.provider_id = provider_id
        self.operation = operation.strip()
        self.kind = kind
        self.retryable = retryable
        self.retry_after = retry_after
        super().__init__(message.strip())
