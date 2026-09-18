"""Dependency-free structured observability and operational health primitives."""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from arbiscan.domain import ProviderId

_LATENCY_WINDOW_SIZE = 256
_RESERVED_LOG_FIELDS = frozenset({"observed_at", "event", "correlation_id", "provider_id"})


def _utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")
    return value.astimezone(UTC)


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class LogSink(Protocol):
    def emit(self, record: StructuredLogRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class StructuredLogRecord:
    observed_at: datetime
    event: str
    correlation_id: str
    provider_id: ProviderId | None = None
    fields: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _utc(self.observed_at, name="observed_at"))
        if not self.event.strip() or not self.correlation_id.strip():
            raise ValueError("event and correlation_id must be non-empty")
        reserved = _RESERVED_LOG_FIELDS.intersection(self.fields)
        if reserved:
            names = ", ".join(sorted(reserved))
            raise ValueError(f"structured log fields use reserved keys: {names}")

    def to_json(self) -> str:
        payload: dict[str, object] = dict(self.fields)
        payload.update(
            {
                "observed_at": self.observed_at.isoformat(),
                "event": self.event,
                "correlation_id": self.correlation_id,
            }
        )
        if self.provider_id is not None:
            payload["provider_id"] = self.provider_id.value
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class InMemoryLogSink:
    def __init__(self) -> None:
        self._records: list[StructuredLogRecord] = []

    @property
    def records(self) -> tuple[StructuredLogRecord, ...]:
        return tuple(self._records)

    def emit(self, record: StructuredLogRecord) -> None:
        if not isinstance(record, StructuredLogRecord):
            raise ValueError("expected StructuredLogRecord")
        self._records.append(record)


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    provider_available: dict[ProviderId, bool] = field(default_factory=dict)
    provider_requests: dict[ProviderId, int] = field(default_factory=dict)
    provider_errors: dict[ProviderId, int] = field(default_factory=dict)
    rate_limit_events: dict[ProviderId, int] = field(default_factory=dict)
    provider_normalization_failures: dict[ProviderId, int] = field(default_factory=dict)
    provider_matching_failures: dict[ProviderId, int] = field(default_factory=dict)
    canonicalization_failures: int = 0
    unmatched_events: int = 0
    ambiguous_events: int = 0
    active_quotes: int = 0
    stale_quotes: int = 0
    opportunities_detected: int = 0
    opportunities_invalidated: int = 0
    detection_latency_seconds: tuple[float, ...] = ()


class MetricsRegistry:
    """Small in-process metrics registry with a stable snapshot contract."""

    def __init__(self) -> None:
        self._provider_available: dict[ProviderId, bool] = {}
        self._provider_requests: dict[ProviderId, int] = {}
        self._provider_errors: dict[ProviderId, int] = {}
        self._rate_limit_events: dict[ProviderId, int] = {}
        self._provider_normalization_failures: dict[ProviderId, int] = {}
        self._provider_matching_failures: dict[ProviderId, int] = {}
        self._counters: dict[str, int] = {}
        self._active_quotes = 0
        self._stale_quotes = 0
        self._latencies: deque[float] = deque(maxlen=_LATENCY_WINDOW_SIZE)

    def provider_request(self, provider_id: ProviderId, *, success: bool) -> None:
        self._provider_requests[provider_id] = self._provider_requests.get(provider_id, 0) + 1
        if not success:
            self._provider_errors[provider_id] = self._provider_errors.get(provider_id, 0) + 1

    def provider_availability(self, provider_id: ProviderId, available: bool) -> None:
        self._provider_available[provider_id] = bool(available)

    def rate_limited(self, provider_id: ProviderId) -> None:
        self._rate_limit_events[provider_id] = self._rate_limit_events.get(provider_id, 0) + 1

    @staticmethod
    def _provider_counter_update(
        values: dict[ProviderId, int],
        provider_id: ProviderId,
        amount: int,
    ) -> None:
        if not isinstance(provider_id, ProviderId):
            raise ValueError("provider_id must be ProviderId")
        if type(amount) is not int or amount < 0:
            raise ValueError("provider metric amount must be a non-negative integer")
        values[provider_id] = values.get(provider_id, 0) + amount

    def provider_normalization_failure(
        self,
        provider_id: ProviderId,
        amount: int = 1,
    ) -> None:
        """Count source-specific strict-normalization failures."""
        self._provider_counter_update(
            self._provider_normalization_failures,
            provider_id,
            amount,
        )

    def provider_matching_failure(
        self,
        provider_id: ProviderId,
        amount: int = 1,
    ) -> None:
        """Count source-specific failures at the canonical event-identity boundary."""
        self._provider_counter_update(
            self._provider_matching_failures,
            provider_id,
            amount,
        )

    def increment(self, name: str, amount: int = 1) -> None:
        allowed = {
            "canonicalization_failures",
            "unmatched_events",
            "ambiguous_events",
            "opportunities_detected",
            "opportunities_invalidated",
        }
        if name not in allowed or type(amount) is not int or amount < 0:
            raise ValueError("invalid metric counter update")
        self._counters[name] = self._counters.get(name, 0) + amount

    def quote_counts(self, *, active: int, stale: int) -> None:
        if type(active) is not int or type(stale) is not int or active < 0 or stale < 0:
            raise ValueError("quote counts must be non-negative integers")
        self._active_quotes, self._stale_quotes = active, stale

    def detection_latency(self, seconds: float) -> None:
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("detection latency must be finite and non-negative")
        self._latencies.append(float(seconds))

    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            provider_available=dict(self._provider_available),
            provider_requests=dict(self._provider_requests),
            provider_errors=dict(self._provider_errors),
            rate_limit_events=dict(self._rate_limit_events),
            provider_normalization_failures=dict(self._provider_normalization_failures),
            provider_matching_failures=dict(self._provider_matching_failures),
            canonicalization_failures=self._counters.get("canonicalization_failures", 0),
            unmatched_events=self._counters.get("unmatched_events", 0),
            ambiguous_events=self._counters.get("ambiguous_events", 0),
            active_quotes=self._active_quotes,
            stale_quotes=self._stale_quotes,
            opportunities_detected=self._counters.get("opportunities_detected", 0),
            opportunities_invalidated=self._counters.get("opportunities_invalidated", 0),
            detection_latency_seconds=tuple(self._latencies),
        )


@dataclass(frozen=True, slots=True)
class HealthPolicy:
    provider_failure_ratio: float = 0.5
    stale_quote_ratio: float = 0.5
    max_detection_latency: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        ratios = (self.provider_failure_ratio, self.stale_quote_ratio)
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in ratios):
            raise ValueError("health ratios must be finite values in [0, 1]")
        if self.max_detection_latency.total_seconds() <= 0:
            raise ValueError("max_detection_latency must be positive")


@dataclass(frozen=True, slots=True)
class HealthReport:
    system: HealthState
    providers: dict[ProviderId, HealthState]
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.system is not HealthState.UNHEALTHY


def assess_health(metrics: MetricsSnapshot, policy: HealthPolicy | None = None) -> HealthReport:
    """Distinguish system degradation from isolated provider degradation."""
    policy = policy or HealthPolicy()
    providers: dict[ProviderId, HealthState] = {}
    reasons: list[str] = []
    provider_ids = (
        set(metrics.provider_requests)
        | set(metrics.provider_errors)
        | set(metrics.provider_available)
    )
    for provider_id in sorted(provider_ids, key=lambda value: value.value):
        requests = metrics.provider_requests.get(provider_id, 0)
        errors = metrics.provider_errors.get(provider_id, 0)
        available = metrics.provider_available.get(provider_id, True)
        ratio = errors / requests if requests else 0.0
        state = HealthState.HEALTHY
        if not available or ratio >= policy.provider_failure_ratio:
            state = HealthState.DEGRADED
            reasons.append(f"provider:{provider_id.value}:degraded")
        providers[provider_id] = state

    total_quotes = metrics.active_quotes + metrics.stale_quotes
    stale_ratio = metrics.stale_quotes / total_quotes if total_quotes else 0.0
    system = HealthState.HEALTHY
    if stale_ratio >= policy.stale_quote_ratio and total_quotes:
        system = HealthState.UNHEALTHY
        reasons.append("system:stale_quote_ratio")
    elif (
        metrics.detection_latency_seconds
        and max(metrics.detection_latency_seconds) > policy.max_detection_latency.total_seconds()
    ):
        system = HealthState.DEGRADED
        reasons.append("system:detection_latency")
    elif any(state is HealthState.DEGRADED for state in providers.values()):
        system = HealthState.DEGRADED

    return HealthReport(system=system, providers=providers, reasons=tuple(reasons))
