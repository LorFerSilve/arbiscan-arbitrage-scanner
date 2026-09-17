"""Phase-16.2 regressions for independent source observations and overlap handling."""

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
    MultiSourceQuoteStore,
    QuoteConsolidationDiagnosticCode,
    RealtimeIngestionPolicy,
    SourceQuoteKey,
)

AS_OF = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
PRICE_PROVIDER = ProviderId("bookmaker:pinnacle")


def _quote(
    transport: str,
    *,
    price: str = "2.10",
    source_seconds: int = 0,
    ingested_seconds: int | None = None,
) -> OddsQuote:
    ingested_offset = source_seconds if ingested_seconds is None else ingested_seconds
    return OddsQuote(
        id=QuoteId(f"quote:{transport}:{source_seconds}:{price}"),
        provider_id=PRICE_PROVIDER,
        transport_provider_id=ProviderId(transport),
        event_id=EventId("event:test"),
        market_id=MarketId("market:test"),
        selection_id=SelectionId("selection:test"),
        decimal_price=Decimal(price),
        source_event_id=f"{transport}:event",
        source_market_id=f"{transport}:market",
        source_selection_id=f"{transport}:selection",
        source_timestamp=AS_OF + timedelta(seconds=source_seconds),
        ingested_at=AS_OF + timedelta(seconds=ingested_offset),
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{transport}:{source_seconds}",
    )


def test_independent_transports_keep_distinct_live_observations() -> None:
    store = MultiSourceQuoteStore(RealtimeIngestionPolicy())
    source_a = _quote("provider:source-a", price="2.10")
    source_b = _quote("provider:source-b", price="2.10")

    result = store.apply((source_a, source_b), observed_at=AS_OF)

    assert result.added_count == 2
    assert len(store) == 2
    assert {version.key.transport_provider_id for version in result.accepted} == {
        ProviderId("provider:source-a"),
        ProviderId("provider:source-b"),
    }


def test_newest_source_observation_wins_one_executable_price_slot() -> None:
    store = MultiSourceQuoteStore(RealtimeIngestionPolicy())
    older = _quote("provider:source-a", price="2.20", source_seconds=0)
    newer = _quote("provider:source-b", price="2.05", source_seconds=5)
    store.apply((older, newer), observed_at=AS_OF + timedelta(seconds=5))

    consolidated = store.consolidate_fresh(as_of=AS_OF + timedelta(seconds=5))

    assert consolidated.quotes == (newer,)
    assert consolidated.diagnostics == ()
    assert len(store) == 2


def test_equal_time_equivalent_observations_consolidate_deterministically() -> None:
    store = MultiSourceQuoteStore(RealtimeIngestionPolicy())
    source_b = _quote("provider:source-b", price="2.10")
    source_a = _quote("provider:source-a", price="2.10")
    store.apply((source_b, source_a), observed_at=AS_OF)

    consolidated = store.consolidate_fresh(as_of=AS_OF)

    assert len(consolidated.quotes) == 1
    assert consolidated.quotes[0].transport_provider_id == ProviderId("provider:source-a")
    assert consolidated.equivalent_overlap_count == 1
    assert consolidated.conflict_count == 0
    assert consolidated.diagnostics[0].code is (
        QuoteConsolidationDiagnosticCode.EQUIVALENT_SOURCE_OBSERVATIONS
    )
    assert consolidated.diagnostics[0].transport_provider_ids == (
        ProviderId("provider:source-a"),
        ProviderId("provider:source-b"),
    )


def test_equal_time_conflicting_observations_fail_closed() -> None:
    store = MultiSourceQuoteStore(RealtimeIngestionPolicy())
    source_a = _quote("provider:source-a", price="2.10")
    source_b = _quote("provider:source-b", price="2.30")
    store.apply((source_a, source_b), observed_at=AS_OF)

    consolidated = store.consolidate_fresh(as_of=AS_OF)

    assert consolidated.quotes == ()
    assert consolidated.conflict_count == 1
    assert consolidated.equivalent_overlap_count == 0
    assert consolidated.diagnostics[0].code is (
        QuoteConsolidationDiagnosticCode.CONFLICTING_SOURCE_OBSERVATIONS
    )


def test_source_specific_invalidation_does_not_remove_other_transport() -> None:
    store = MultiSourceQuoteStore(RealtimeIngestionPolicy())
    source_a = _quote("provider:source-a", price="2.10")
    source_b = _quote("provider:source-b", price="2.10")
    store.apply((source_a, source_b), observed_at=AS_OF)

    excluded = (SourceQuoteKey.from_quote(source_a),)
    consolidated = store.consolidate_fresh(as_of=AS_OF, excluded_keys=excluded)

    assert consolidated.quotes == (source_b,)
    assert consolidated.diagnostics == ()


def test_same_transport_versions_independently_from_overlapping_source() -> None:
    store = MultiSourceQuoteStore(RealtimeIngestionPolicy())
    source_a_first = _quote("provider:source-a", price="2.10")
    source_b = _quote("provider:source-b", price="2.15")
    store.apply((source_a_first, source_b), observed_at=AS_OF)

    source_a_update = _quote("provider:source-a", price="2.20", source_seconds=3)
    update = store.apply((source_a_update,), observed_at=AS_OF + timedelta(seconds=3))

    assert update.updated_count == 1
    assert update.accepted[0].revision == 2
    assert len(store) == 2
    assert store.consolidate_fresh(as_of=AS_OF + timedelta(seconds=3)).quotes == (source_a_update,)
