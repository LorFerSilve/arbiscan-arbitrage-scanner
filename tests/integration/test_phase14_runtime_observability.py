"""Phase-14 runtime wiring regression coverage."""

import asyncio

from arbiscan.providers.synthetic import build_phase5_synthetic_scenario
from arbiscan.services import RealtimeScanner


def test_realtime_cycle_updates_phase14_metrics_and_structured_log() -> None:
    scenario = build_phase5_synthetic_scenario()
    scanner = RealtimeScanner(
        adapters=scenario.adapters,
        registry=scenario.registry,
        sport=scenario.registry.events[0].sport,
        clock=lambda: scenario.as_of,
    )

    cycle = asyncio.run(scanner.run_cycle())
    snapshot = scanner.metrics_registry.snapshot()

    assert snapshot.provider_requests
    assert set(snapshot.provider_requests) == {adapter.provider.id for adapter in scenario.adapters}
    assert snapshot.active_quotes == len(cycle.fresh_quotes)
    assert snapshot.stale_quotes == cycle.metrics.stale_quote_count
    assert snapshot.canonicalization_failures == cycle.metrics.normalization_issue_count
    assert snapshot.opportunities_detected == len(cycle.opportunities)
    assert scanner.log_sink.records
    record = scanner.log_sink.records[-1]
    assert record.event == "scanner.cycle.completed"
    assert record.observed_at == cycle.metrics.detected_at
    assert record.fields["opportunity_count"] == len(cycle.opportunities)
