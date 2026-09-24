"""End-to-end Phase-10 freshness and stale-signal regressions."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta

from arbiscan.domain import EventStatus, Provider, Sport
from arbiscan.ingestion import RealtimeIngestionPolicy
from arbiscan.marketbook import MarketBookDiagnosticCode
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.models import (
    CanonicalIdHooks,
    OddsSnapshot,
    ProviderCapabilities,
    ProviderHealth,
    RateLimitSnapshot,
    SourceCompetition,
    SourceEvent,
)
from arbiscan.providers.synthetic import build_phase5_synthetic_scenario
from arbiscan.services import RealtimeScanner


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class SuspendableAdapter(ProviderAdapter):
    """Delegate adapter that can turn returned markets inactive between cycles."""

    def __init__(self, base: ProviderAdapter) -> None:
        self.base = base
        self.suspended = False

    @property
    def provider(self) -> Provider:
        return self.base.provider

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self.base.capabilities

    @property
    def canonical_id_hooks(self) -> CanonicalIdHooks | None:
        return self.base.canonical_id_hooks

    async def supported_sports(self) -> tuple[Sport, ...]:
        return await self.base.supported_sports()

    async def discover_competitions(self, sport: Sport) -> tuple[SourceCompetition, ...]:
        return await self.base.discover_competitions(sport)

    async def discover_events(
        self,
        competition_external_id: str,
        *,
        starts_after: datetime | None = None,
        starts_before: datetime | None = None,
    ) -> tuple[SourceEvent, ...]:
        return await self.base.discover_events(
            competition_external_id,
            starts_after=starts_after,
            starts_before=starts_before,
        )

    async def fetch_odds(self, external_event_id: str) -> OddsSnapshot | None:
        snapshot = await self.base.fetch_odds(external_event_id)
        if snapshot is None or not self.suspended:
            return snapshot
        return replace(
            snapshot,
            markets=tuple(
                replace(market, source_status="suspended") for market in snapshot.markets
            ),
        )

    def stream_odds(self, external_event_ids: tuple[str, ...]) -> AsyncIterator[OddsSnapshot]:
        return self.base.stream_odds(external_event_ids)

    async def health(self) -> ProviderHealth:
        return await self.base.health()

    async def rate_limit(self) -> RateLimitSnapshot | None:
        return await self.base.rate_limit()


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


def test_realtime_scanner_rejects_fresh_quotes_for_non_prematch_events() -> None:
    scenario = build_phase5_synthetic_scenario()
    registry = replace(
        scenario.registry,
        events=tuple(replace(event, status=EventStatus.LIVE) for event in scenario.registry.events),
    )
    scanner = RealtimeScanner(
        adapters=scenario.adapters,
        registry=registry,
        sport=Sport.FOOTBALL,
        policy=RealtimeIngestionPolicy(freshness_window=scenario.freshness_window),
        clock=MutableClock(scenario.as_of),
    )

    cycle = asyncio.run(scanner.run_cycle())

    assert cycle.fresh_quotes
    assert cycle.market_books == ()
    assert cycle.opportunities == ()
    assert MarketBookDiagnosticCode.EVENT_NOT_PREMATCH in {
        item.code for item in cycle.market_book_diagnostics
    }


def test_explicit_provider_suspension_invalidates_live_quotes_immediately() -> None:
    scenario = build_phase5_synthetic_scenario()
    clock = MutableClock(scenario.as_of)
    adapters = tuple(SuspendableAdapter(adapter) for adapter in scenario.adapters)
    scanner = RealtimeScanner(
        adapters=adapters,
        registry=scenario.registry,
        sport=scenario.registry.events[0].sport,
        policy=RealtimeIngestionPolicy(
            freshness_window=scenario.freshness_window,
            max_concurrency=3,
        ),
        clock=clock,
    )

    first = asyncio.run(scanner.run_cycle())
    assert first.opportunities
    assert first.fresh_quotes

    for adapter in adapters:
        adapter.suspended = True
    clock.value = scenario.as_of + timedelta(seconds=1)
    second = asyncio.run(scanner.run_cycle())

    assert second.source_invalidated_quote_keys
    assert second.metrics.source_invalidated_quote_count > 0
    assert second.fresh_quotes == ()
    assert second.market_books == ()
    assert second.opportunities == ()
    assert second.evictions.evicted == ()


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
