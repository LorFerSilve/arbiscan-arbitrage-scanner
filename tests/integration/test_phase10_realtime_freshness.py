"""End-to-end Phase-10 freshness and stale-signal regressions."""

import asyncio
from datetime import datetime, timedelta

from arbiscan.ingestion import RealtimeIngestionPolicy
from arbiscan.providers.synthetic import build_phase5_synthetic_scenario
from arbiscan.services import RealtimeScanner


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def test_realtime_scanner_expires_old_arbitrage_when_provider_data_stops_advancing() -> None:
    scenario = build_phase5_synthetic_scenario()
    clock = MutableClock(scenario.as_of)
    policy = RealtimeIngestionPolicy(
        poll_interval=timedelta(seconds=5),
        freshness_window=scenario.freshness_window,
        max_concurrency=3,
        clock_skew_tolerance=timedelta(seconds=5),
    )
    scanner = RealtimeScanner(
        adapters=scenario.adapters,
        registry=scenario.registry,
        sport=scenario.registry.events[0].sport,
        policy=policy,
        clock=clock,
    )

    first = asyncio.run(scanner.run_cycle())

    assert first.opportunities
    assert first.market_books
    assert first.fresh_quotes
    assert first.metrics.quote_age_max is not None
    assert first.metrics.ingestion_to_detection_latency_max is not None
    assert first.metrics.stale_quote_count == 0

    clock.value = scenario.as_of + scenario.freshness_window + timedelta(seconds=1)
    second = asyncio.run(scanner.run_cycle())

    assert second.opportunities == ()
    assert second.market_books == ()
    assert second.fresh_quotes == ()
    assert second.evictions.evicted
    assert second.metrics.stale_quote_count == len(second.evictions.evicted)
    assert second.metrics.opportunity_count == 0


def test_realtime_cycle_exposes_provider_latency_error_and_update_metrics() -> None:
    scenario = build_phase5_synthetic_scenario()
    clock = MutableClock(scenario.as_of)
    policy = RealtimeIngestionPolicy(
        freshness_window=scenario.freshness_window,
        max_concurrency=2,
    )
    scanner = RealtimeScanner(
        adapters=scenario.adapters,
        registry=scenario.registry,
        sport=scenario.registry.events[0].sport,
        policy=policy,
        clock=clock,
    )

    cycle = asyncio.run(scanner.run_cycle())

    assert len(cycle.metrics.provider_metrics) == len(scenario.adapters)
    assert all(metric.request_latency >= timedelta(0) for metric in cycle.metrics.provider_metrics)
    assert cycle.metrics.provider_error_rate >= 0
    assert cycle.metrics.provider_error_rate <= 1
    assert cycle.metrics.current_fresh_quote_count == len(cycle.fresh_quotes)
    assert cycle.metrics.market_book_count == len(cycle.market_books)
    assert cycle.metrics.opportunity_count == len(cycle.opportunities)
