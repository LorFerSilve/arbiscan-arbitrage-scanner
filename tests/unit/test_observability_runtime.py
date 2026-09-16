from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from arbiscan.domain import ProviderId
from arbiscan.observability import (
    HealthPolicy,
    HealthState,
    InMemoryLogSink,
    MetricsRegistry,
    StructuredLogRecord,
    assess_health,
)


def _assert_value_error(operation: Callable[[], object], expected_message: str) -> None:
    try:
        operation()
    except ValueError as exc:
        assert expected_message in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_structured_log_is_correlated_and_machine_readable() -> None:
    sink = InMemoryLogSink()
    record = StructuredLogRecord(
        observed_at=datetime(2026, 9, 15, 20, tzinfo=UTC),
        event="provider.request",
        correlation_id="batch-42",
        provider_id=ProviderId("provider-a"),
        fields={"operation": "odds", "success": True},
    )
    sink.emit(record)

    assert sink.records == (record,)
    assert '"correlation_id":"batch-42"' in record.to_json()
    assert '"provider_id":"provider-a"' in record.to_json()


def test_isolated_provider_failure_degrades_without_making_system_unready() -> None:
    metrics = MetricsRegistry()
    provider = ProviderId("provider-a")
    metrics.provider_availability(provider, False)
    metrics.provider_request(provider, success=False)
    metrics.quote_counts(active=20, stale=0)

    report = assess_health(metrics.snapshot())

    assert report.system is HealthState.DEGRADED
    assert report.providers[provider] is HealthState.DEGRADED
    assert report.ready is True


def test_unavailable_provider_without_request_history_is_reported() -> None:
    metrics = MetricsRegistry()
    provider = ProviderId("provider-a")
    metrics.provider_availability(provider, False)

    report = assess_health(metrics.snapshot())

    assert report.providers[provider] is HealthState.DEGRADED
    assert report.system is HealthState.DEGRADED
    assert report.ready is True


def test_stale_quote_failure_is_system_unhealthy() -> None:
    metrics = MetricsRegistry()
    metrics.quote_counts(active=2, stale=8)

    report = assess_health(metrics.snapshot(), HealthPolicy(stale_quote_ratio=0.5))

    assert report.system is HealthState.UNHEALTHY
    assert report.ready is False
    assert "system:stale_quote_ratio" in report.reasons


def test_detection_latency_is_visible_as_system_degradation() -> None:
    metrics = MetricsRegistry()
    metrics.quote_counts(active=10, stale=0)
    metrics.detection_latency(3.0)

    report = assess_health(
        metrics.snapshot(),
        HealthPolicy(max_detection_latency=timedelta(seconds=2)),
    )

    assert report.system is HealthState.DEGRADED
    assert "system:detection_latency" in report.reasons


def test_detection_latency_rejects_non_finite_values() -> None:
    metrics = MetricsRegistry()

    _assert_value_error(lambda: metrics.detection_latency(float("nan")), "finite and non-negative")
    _assert_value_error(lambda: metrics.detection_latency(float("inf")), "finite and non-negative")


def test_health_policy_rejects_non_finite_ratios() -> None:
    _assert_value_error(lambda: HealthPolicy(provider_failure_ratio=float("nan")), "finite values")
    _assert_value_error(lambda: HealthPolicy(stale_quote_ratio=float("inf")), "finite values")


def test_metrics_cover_phase_14_minimum_surface() -> None:
    metrics = MetricsRegistry()
    provider = ProviderId("provider-a")
    metrics.provider_availability(provider, True)
    metrics.provider_request(provider, success=True)
    metrics.provider_request(provider, success=False)
    metrics.rate_limited(provider)
    metrics.increment("canonicalization_failures")
    metrics.increment("unmatched_events", 2)
    metrics.increment("ambiguous_events")
    metrics.increment("opportunities_detected", 3)
    metrics.increment("opportunities_invalidated")
    metrics.quote_counts(active=11, stale=4)
    metrics.detection_latency(0.125)

    snapshot = metrics.snapshot()
    assert snapshot.provider_available[provider] is True
    assert snapshot.provider_requests[provider] == 2
    assert snapshot.provider_errors[provider] == 1
    assert snapshot.rate_limit_events[provider] == 1
    assert snapshot.canonicalization_failures == 1
    assert snapshot.unmatched_events == 2
    assert snapshot.ambiguous_events == 1
    assert snapshot.active_quotes == 11
    assert snapshot.stale_quotes == 4
    assert snapshot.opportunities_detected == 3
    assert snapshot.opportunities_invalidated == 1
    assert snapshot.detection_latency_seconds == (0.125,)
