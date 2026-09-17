"""Phase-16.2 persistence regressions for transport provenance."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    Opportunity,
    OpportunityId,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
)
from arbiscan.persistence import SqliteAuditStore


def _quote(
    *,
    quote_id: str,
    price_provider: str,
    transport_provider: str,
    selection: str,
    at: datetime,
) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(quote_id),
        provider_id=ProviderId(price_provider),
        transport_provider_id=ProviderId(transport_provider),
        event_id=EventId("event:phase16"),
        market_id=MarketId("market:phase16"),
        selection_id=SelectionId(selection),
        decimal_price=Decimal("2.10"),
        source_event_id=f"{transport_provider}:event",
        source_market_id=f"{transport_provider}:market",
        source_selection_id=f"{transport_provider}:{selection}",
        source_timestamp=at,
        ingested_at=at,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{quote_id}",
    )


def test_reconstructed_opportunity_preserves_price_and_transport_providers(
    tmp_path: Path,
) -> None:
    at = datetime(2026, 9, 17, 2, 0, tzinfo=UTC)
    quotes = (
        _quote(
            quote_id="quote:home",
            price_provider="bookmaker:alpha",
            transport_provider="transport:one",
            selection="selection:home",
            at=at,
        ),
        _quote(
            quote_id="quote:away",
            price_provider="bookmaker:beta",
            transport_provider="transport:two",
            selection="selection:away",
            at=at,
        ),
    )
    opportunity = Opportunity(
        id=OpportunityId("opportunity:phase16"),
        event_id=EventId("event:phase16"),
        market_id=MarketId("market:phase16"),
        quote_ids=tuple(quote.id for quote in quotes),
        implied_probability_sum=Decimal("0.95"),
        theoretical_profit_margin=Decimal("0.05"),
        detected_at=at,
    )
    store = SqliteAuditStore(tmp_path / "phase16.db")
    store.migrate()
    store.persist_opportunity(opportunity, quotes)

    restored = store.reconstruct_opportunity(opportunity.id.value)

    assert tuple(quote.provider_id for quote in restored.quotes) == tuple(
        quote.provider_id for quote in quotes
    )
    assert tuple(quote.transport_provider_id for quote in restored.quotes) == tuple(
        quote.transport_provider_id for quote in quotes
    )
