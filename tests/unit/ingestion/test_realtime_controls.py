"""Focused regressions for Phase-10 realtime scheduling and freshness control."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import ClassVar

from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    Provider,
    ProviderId,
    ProviderKind,
    QuoteId,
    QuoteStatus,
    SelectionId,
    Sport,
)
from arbiscan.ingestion import LiveQuoteStore, RealtimeIngestionPolicy, RealtimeIngestionRuntime
from arbiscan.matching import CanonicalRegistry
from arbiscan.providers.fake import FakeProvider, FakeProviderFixtures
from arbiscan.services import RealtimeScanner

AS_OF = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class TrackingFakeProvider(FakeProvider):
    active_calls: ClassVar[int] = 0
    maximum_active_calls: ClassVar[int] = 0

    @classmethod
    def reset_tracking(cls) -> None:
        cls.active_calls = 0
        cls.maximum_active_calls = 0

    async def supported_sports(self) -> tuple[Sport, ...]:
        type(self).active_calls += 1
        type(self).maximum_active_calls = max(
            type(self).maximum_active_calls,
            type(self).active_calls,
        )
        try:
            await asyncio.sleep(0.01)
            return await super().supported_sports()
        finally:
            type(self).active_calls -= 1


def _quote_without_source_timestamp(*, ingested_at: datetime, quote_id: str) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(quote_id),
        provider_id=ProviderId("provider:no-source-clock"),
        event_id=EventId("event:test"),
        market_id=MarketId("market:test"),
        selection_id=SelectionId("selection:test"),
        decimal_price=Decimal("2.10"),
        source_event_id="source:event",
        source_market_id="source:market",
        source_selection_id="source:selection",
        source_timestamp=None,
        ingested_at=ingested_at,
        status=QuoteStatus.ACTIVE,
        trace_id=quote_id,
    )


def test_new_ingestion_renews_quote_when_provider_has_no_source_timestamp() -> None:
    policy = RealtimeIngestionPolicy(freshness_window=timedelta(seconds=30))
    store = LiveQuoteStore(policy)
    first = _quote_without_source_timestamp(ingested_at=AS_OF, quote_id="quote:first")
    refreshed = _quote_without_source_timestamp(
        ingested_at=AS_OF + timedelta(seconds=20),
        quote_id="quote:refreshed",
    )

    first_result = store.apply((first,), observed_at=AS_OF)
    second_result = store.apply(
        (refreshed,),
        observed_at=AS_OF + timedelta(seconds=20),
    )

    assert first_result.accepted[0].revision == 1
    assert second_result.updated_count == 1
    assert second_result.accepted[0].revision == 2
    assert store.fresh_quotes(as_of=AS_OF + timedelta(seconds=31)) == (refreshed,)


def test_provider_polling_never_exceeds_configured_concurrency() -> None:
    TrackingFakeProvider.reset_tracking()
    adapters = tuple(
        TrackingFakeProvider(
            provider=Provider(
                id=ProviderId(f"provider:tracked-{index}"),
                name=f"Tracked {index}",
                kind=ProviderKind.SYNTHETIC,
            ),
            fixtures=FakeProviderFixtures(sports=(Sport.FOOTBALL,)),
        )
        for index in range(4)
    )
    runtime = RealtimeIngestionRuntime(
        policy=RealtimeIngestionPolicy(max_concurrency=2),
        clock=MutableClock(AS_OF),
    )

    asyncio.run(runtime.poll_once(adapters, Sport.FOOTBALL))

    assert TrackingFakeProvider.maximum_active_calls == 2
    assert TrackingFakeProvider.active_calls == 0


def test_poll_scheduler_drops_missed_intervals_instead_of_building_backlog() -> None:
    clock = MutableClock(AS_OF)
    policy = RealtimeIngestionPolicy(poll_interval=timedelta(seconds=5))
    registry = CanonicalRegistry(
        competitions=(),
        participants=(),
        events=(),
        markets=(),
        selections=(),
    )
    scanner = RealtimeScanner(
        adapters=(),
        registry=registry,
        sport=Sport.FOOTBALL,
        policy=policy,
        clock=clock,
    )

    async def exercise() -> tuple[int, int]:
        cycles = scanner.cycles()
        first = await anext(cycles)
        clock.value = AS_OF + timedelta(seconds=12)
        second = await anext(cycles)
        return (
            first.metrics.missed_poll_intervals_total,
            second.metrics.missed_poll_intervals_total,
        )

    first_missed, second_missed = asyncio.run(exercise())

    assert first_missed == 0
    assert second_missed == 2
