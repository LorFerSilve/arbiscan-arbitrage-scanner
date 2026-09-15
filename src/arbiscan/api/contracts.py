"""Stable, transport-neutral API contracts for ArbiScan clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class ErrorCode(StrEnum):
    """Machine-readable API error codes kept stable across transports."""

    BAD_REQUEST = "bad_request"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    NOT_READY = "not_ready"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class ApiError:
    """Public error envelope; details must never contain credentials or secrets."""

    code: ErrorCode
    message: str
    correlation_id: str | None = None
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PageRequest:
    """Offset pagination shared by collection endpoints."""

    offset: int = 0
    limit: int = 50

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError("offset must be >= 0")
        if not 1 <= self.limit <= 200:
            raise ValueError("limit must be between 1 and 200")


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    """Stable paginated response independent of persistence implementation."""

    items: tuple[T, ...]
    offset: int
    limit: int
    total: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


@dataclass(frozen=True, slots=True)
class HealthResponse:
    status: str
    version: str


@dataclass(frozen=True, slots=True)
class ReadinessResponse:
    ready: bool
    checks: dict[str, bool]


@dataclass(frozen=True, slots=True)
class ProviderStatusResponse:
    provider_id: str
    available: bool
    last_success_at: str | None = None
    last_error_at: str | None = None


@dataclass(frozen=True, slots=True)
class SportResponse:
    sport: str


@dataclass(frozen=True, slots=True)
class EventSummaryResponse:
    event_id: str
    sport: str
    competition: str
    participant_names: tuple[str, ...]
    scheduled_start: str
    status: str


@dataclass(frozen=True, slots=True)
class OddsResponse:
    quote_id: str
    event_id: str
    market_id: str
    selection_id: str
    provider_id: str
    decimal_price: str
    status: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class OpportunitySummaryResponse:
    opportunity_id: str
    event_id: str
    market_id: str
    implied_probability_sum: str
    guaranteed_profit_rate: str
    detected_at: str


@dataclass(frozen=True, slots=True)
class OpportunityDetailResponse:
    opportunity: OpportunitySummaryResponse
    quote_ids: tuple[str, ...]
    evidence_available: bool


@dataclass(frozen=True, slots=True)
class ConfigurationStatusResponse:
    scanner_only: bool
    authentication_required: bool
    rate_limiting_enabled: bool


@dataclass(frozen=True, slots=True)
class MetricsResponse:
    values: dict[str, int | float]
