"""Phase-16.2 transport-aware live-state regressions."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
)
from arbiscan.ingestion import (
    ConsolidationDiagnosticCode,
    MultiSourceLiveQuoteStore,
    RealtimeIngestionPolicy,
    SourceObservationKey,
)

AS_OF = datetime(2026, 9, 17, 2, 0, tzinfo=UTC)


def _quote(*, transport: str, price: str, seconds_old: int, suffix: str) -> OddsQuote:
    timestamp = AS_OF - timedelta(seconds=seconds_old)
    return OddsQuote(
        id=QuoteId(f"quote:{transport}:{suffix}"),
        provider_id=ProviderId("bookmaker:shared"),
        transport_provider_id=ProviderId(f"transport:{transport}"),
        event_id=EventId("event:1"),
        market_id=MarketId("market:1"),
        selection_id=SelectionId("selection:home"),
        decimal_price=Decimal(price),
        source_event_id=f"{transport}:event",
        source_market_id=f"{transport}:market",
        source_selection_id=f"{transport}:selection",
        source_timestamp=timestamp,
        ingested_at=timestamp,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{transport}:{suffix}",
    )


def _store() -> MultiSourceLiveQuoteStore:
    return MultiSourceLiveQuoteStore(RealtimeIngestionPolicy(freshness_window=timedelta(minutes=2)))


def test_independent_transports_remain_distinct_until_consolidation() -> None:
    store = _store()
    alpha = _quote(transport="alpha", price="2.20", seconds_old=0, suffix="a")
    beta = _quote(transport="beta", price="2.20", seconds_old=0, suffix="b")

    result = store.apply((alpha, beta), observed_at=AS_OF)

    assert result.added_count == 2
    assert len(store) == 2
    assert store.fresh_observations(as_of=AS_OF) == (alpha, beta)
    assert store.fresh_quotes(as_of=AS_OF) == (alpha,)
    consolidation = store.last_consolidation_result
    assert consolidation.equivalent_overlap_count == 1
    assert consolidation.conflict_count == 0
    assert {item.code for item in consolidation.diagnostics} == {
        ConsolidationDiagnosticCode.EQUIVALENT_OVERLAP
    }


def test_newest_transport_observation_wins_executable_slot() -> None:
    store = _store()
    older = _quote(transport="alpha", price="2.10", seconds_old=10, suffix="old")
    newer = _quote(transport="beta", price="2.25", seconds_old=0, suffix="new")

    store.apply((older, newer), observed_at=AS_OF)

    assert len(store.fresh_observations(as_of=AS_OF)) == 2
    assert store.fresh_quotes(as_of=AS_OF) == (newer,)
    assert store.last_consolidation_result.conflict_count == 0


def test_equal_time_material_conflict_fails_closed() -> None:
    store = _store()
    alpha = _quote(transport="alpha", price="2.20", seconds_old=0, suffix="a")
    beta = _quote(transport="beta", price="2.30", seconds_old=0, suffix="b")

    store.apply((alpha, beta), observed_at=AS_OF)

    assert store.fresh_quotes(as_of=AS_OF) == ()
    consolidation = store.last_consolidation_result
    assert consolidation.conflict_count == 1
    assert {item.code for item in consolidation.diagnostics} == {
        ConsolidationDiagnosticCode.MATERIAL_CONFLICT
    }


def test_transport_specific_invalidation_does_not_remove_independent_feed() -> None:
    store = _store()
    alpha = _quote(transport="alpha", price="2.20", seconds_old=0, suffix="a")
    beta = _quote(transport="beta", price="2.25", seconds_old=0, suffix="b")
    store.apply((alpha, beta), observed_at=AS_OF)

    store.invalidate_observations((SourceObservationKey.from_quote(beta),))

    assert store.fresh_observations(as_of=AS_OF) == (alpha,)
    assert store.fresh_quotes(as_of=AS_OF) == (alpha,)
