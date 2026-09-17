"""Regression tests for canonical odds-quote provenance requirements."""

from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.domain import (
    DomainValidationError,
    EventId,
    MarketId,
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
)


def test_quote_requires_trace_or_raw_source_reference() -> None:
    try:
        OddsQuote(
            id=QuoteId("quote:no-audit-reference"),
            provider_id=ProviderId("provider:a"),
            event_id=EventId("event:1"),
            market_id=MarketId("market:1"),
            selection_id=SelectionId("selection:1"),
            decimal_price=Decimal("2.10"),
            source_event_id="event-1",
            source_market_id="market-1",
            source_selection_id="selection-1",
            ingested_at=datetime(2026, 9, 13, 0, 0, tzinfo=UTC),
            status=QuoteStatus.ACTIVE,
        )
    except DomainValidationError:
        pass
    else:
        raise AssertionError("quote without trace/raw-source provenance must be rejected")


def test_quote_accepts_trace_id_as_audit_reference() -> None:
    quote = OddsQuote(
        id=QuoteId("quote:traceable"),
        provider_id=ProviderId("provider:a"),
        event_id=EventId("event:1"),
        market_id=MarketId("market:1"),
        selection_id=SelectionId("selection:1"),
        decimal_price=Decimal("2.10"),
        source_event_id="event-1",
        source_market_id="market-1",
        source_selection_id="selection-1",
        ingested_at=datetime(2026, 9, 13, 0, 0, tzinfo=UTC),
        status=QuoteStatus.ACTIVE,
        trace_id="trace-123",
    )

    assert quote.trace_id == "trace-123"
    assert quote.raw_source_reference is None


def test_direct_source_defaults_transport_identity_to_price_provider() -> None:
    provider_id = ProviderId("bookmaker:direct")
    quote = OddsQuote(
        id=QuoteId("quote:direct"),
        provider_id=provider_id,
        event_id=EventId("event:1"),
        market_id=MarketId("market:1"),
        selection_id=SelectionId("selection:1"),
        decimal_price=Decimal("2.10"),
        source_event_id="event-1",
        source_market_id="market-1",
        source_selection_id="selection-1",
        ingested_at=datetime(2026, 9, 17, 0, 0, tzinfo=UTC),
        status=QuoteStatus.ACTIVE,
        trace_id="trace-direct",
    )

    assert quote.transport_provider_id == provider_id


def test_aggregated_quote_preserves_transport_separately_from_price_origin() -> None:
    quote = OddsQuote(
        id=QuoteId("quote:aggregated"),
        provider_id=ProviderId("bookmaker:pinnacle"),
        transport_provider_id=ProviderId("provider:aggregator-a"),
        event_id=EventId("event:1"),
        market_id=MarketId("market:1"),
        selection_id=SelectionId("selection:1"),
        decimal_price=Decimal("2.10"),
        source_event_id="event-1",
        source_market_id="market-1",
        source_selection_id="selection-1",
        ingested_at=datetime(2026, 9, 17, 0, 0, tzinfo=UTC),
        status=QuoteStatus.ACTIVE,
        trace_id="trace-aggregated",
    )

    assert quote.provider_id == ProviderId("bookmaker:pinnacle")
    assert quote.transport_provider_id == ProviderId("provider:aggregator-a")
