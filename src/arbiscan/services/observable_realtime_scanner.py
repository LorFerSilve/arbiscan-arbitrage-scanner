"""Observable application-facing realtime scanner.

This adapter keeps Phase-14 telemetry at the application boundary while the
Phase-10 scanner remains responsible for ingestion and arbitrage semantics.
"""

from __future__ import annotations

from arbiscan.observability import InMemoryLogSink, MetricsRegistry, StructuredLogRecord
from arbiscan.services.realtime_scanner import RealtimeScanCycle, RealtimeScanner as CoreRealtimeScanner


class RealtimeScanner(CoreRealtimeScanner):
    """Realtime scanner whose real cycles feed the Phase-14 observability surface."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__()

    @property
    def metrics_registry(self) -> MetricsRegistry:
        registry = getattr(self, "_phase14_metrics_registry", None)
        if registry is None:
            registry = MetricsRegistry()
            self._phase14_metrics_registry = registry
        return registry

    @property
    def log_sink(self) -> InMemoryLogSink:
        sink = getattr(self, "_phase14_log_sink", None)
        if sink is None:
            sink = InMemoryLogSink()
            self._phase14_log_sink = sink
        return sink

    async def run_cycle(self) -> RealtimeScanCycle:
        cycle = await super().run_cycle()
        registry = self.metrics_registry

        for metric in cycle.metrics.provider_metrics:
            registry.provider_request(
                metric.provider_id,
                success=metric.issue_count == 0 and not metric.throttled,
            )
            registry.provider_availability(
                metric.provider_id,
                metric.health_state.value != "unavailable",
            )
            if metric.throttled:
                registry.rate_limited(metric.provider_id)

        registry.increment("canonicalization_failures", cycle.metrics.normalization_issue_count)
        registry.increment("opportunities_detected", cycle.metrics.opportunity_count)
        registry.quote_counts(
            active=cycle.metrics.current_fresh_quote_count,
            stale=cycle.metrics.stale_quote_count,
        )
        latency = cycle.metrics.ingestion_to_detection_latency_max
        if latency is not None:
            registry.detection_latency(latency.total_seconds())

        self.log_sink.emit(
            StructuredLogRecord(
                observed_at=cycle.metrics.detected_at,
                event="scanner.cycle.completed",
                correlation_id=cycle.metrics.started_at.isoformat(),
                fields={
                    "provider_issue_count": cycle.metrics.provider_issue_count,
                    "normalization_issue_count": cycle.metrics.normalization_issue_count,
                    "fresh_quote_count": cycle.metrics.current_fresh_quote_count,
                    "stale_quote_count": cycle.metrics.stale_quote_count,
                    "opportunity_count": cycle.metrics.opportunity_count,
                    "throttling_events": cycle.metrics.throttling_events,
                },
            )
        )
        return cycle
