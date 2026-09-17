"""Phase 16.2 regression tests for multi-source live quote state."""

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
from arbiscan.ingestion import LiveQuoteStore, QuoteKey, RealtimeIngestionPolicy

AS_OF = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)
PRICE_PROVIDER = ProviderId("bookmaker:shared")
THE_ODDS_API = ProviderId("provider:the-odds-api")
ODDSPAPI = ProviderId("provider:oddspapi")


def _quote(source_provider: ProviderId, suffix: str) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:{suffix}"),
        provider_id=PRICE_PROVIDER,
        source_provider_id=source_provider,
        event_id=EventId("event:shared"),
        market_id=MarketId("market:shared"),
        selection_id=SelectionId("selection:shared"),
        decimal_price=Decimal("2.10"),
        source_event_id=f"{source_provider.value}:event",
        source_market_id=f"{source_provider.value}:market",
        source_selection_id=f"{source_provider.value}:selection",
        source_timestamp=AS_OF - timedelta(seconds=5),
        ingested_at=AS_OF,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{suffix}",
    )


def test_live_store_keeps_same_bookmaker_observations_from_two_transports() -> None:
    policy = RealtimeIngestionPolicy(freshness_window=timedelta(minutes=2))
    store = LiveQuoteStore(policy)
    the_odds = _quote(THE_ODDS_API, "the-odds")
    oddspapi = _quote(ODDSPAPI, "oddspapi")

    applied = store.apply((the_odds, oddspapi), observed_at=AS_OF)

    assert applied.added_count == 2
    assert applied.updated_count == 0
    assert applied.duplicate_count == 0
    assert len(store) == 2
    assert set(store.fresh_quotes(as_of=AS_OF)) == {the_odds, oddspapi}
    assert QuoteKey.from_quote(the_odds) != QuoteKey.from_quote(oddspapi)
    assert {version.key.source_provider_id for version in applied.accepted} == {
        THE_ODDS_API,
        ODDSPAPI,
    }
