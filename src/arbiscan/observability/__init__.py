"""Backend-neutral observability primitives."""

from arbiscan.observability.provider import (
    InMemoryProviderTelemetry,
    NullProviderTelemetry,
    ProviderTelemetryEvent,
    ProviderTelemetryOutcome,
    ProviderTelemetrySink,
)
from arbiscan.observability.runtime import (
    HealthPolicy,
    HealthReport,
    HealthState,
    InMemoryLogSink,
    LogSink,
    MetricsRegistry,
    MetricsSnapshot,
    StructuredLogRecord,
    assess_health,
)

__all__ = [
    "HealthPolicy",
    "HealthReport",
    "HealthState",
    "InMemoryLogSink",
    "InMemoryProviderTelemetry",
    "LogSink",
    "MetricsRegistry",
    "MetricsSnapshot",
    "NullProviderTelemetry",
    "ProviderTelemetryEvent",
    "ProviderTelemetryOutcome",
    "ProviderTelemetrySink",
    "StructuredLogRecord",
    "assess_health",
]
