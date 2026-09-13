"""Backend-neutral telemetry for provider adapter calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from arbiscan.domain import ProviderId


class ProviderTelemetryOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class ProviderTelemetryEvent:
    provider_id: ProviderId
    operation: str
    observed_at: datetime
    outcome: ProviderTelemetryOutcome
    http_status: int | None = None
    item_count: int | None = None
    quota_remaining: int | None = None
    quota_used: int | None = None
    request_cost: int | None = None
    error_kind: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise ValueError("provider_id must be ProviderId")
        if not isinstance(self.operation, str) or not self.operation.strip():
            raise ValueError("operation must be non-empty text")
        if not isinstance(self.observed_at, datetime):
            raise ValueError("observed_at must be datetime")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))
        if not isinstance(self.outcome, ProviderTelemetryOutcome):
            raise ValueError("outcome must be ProviderTelemetryOutcome")
        if self.http_status is not None and (
            type(self.http_status) is not int or not 100 <= self.http_status <= 599
        ):
            raise ValueError("http_status must be in [100, 599]")
        for field_name in ("item_count", "quota_remaining", "quota_used", "request_cost"):
            value = getattr(self, field_name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.error_kind is not None and (
            not isinstance(self.error_kind, str) or not self.error_kind.strip()
        ):
            raise ValueError("error_kind must be non-empty text when provided")


class ProviderTelemetrySink(Protocol):
    def emit(self, event: ProviderTelemetryEvent) -> None: ...


class NullProviderTelemetry:
    def emit(self, event: ProviderTelemetryEvent) -> None:
        _ = event


class InMemoryProviderTelemetry:
    def __init__(self) -> None:
        self._events: list[ProviderTelemetryEvent] = []

    @property
    def events(self) -> tuple[ProviderTelemetryEvent, ...]:
        return tuple(self._events)

    def emit(self, event: ProviderTelemetryEvent) -> None:
        if not isinstance(event, ProviderTelemetryEvent):
            raise ValueError("expected ProviderTelemetryEvent")
        self._events.append(event)
