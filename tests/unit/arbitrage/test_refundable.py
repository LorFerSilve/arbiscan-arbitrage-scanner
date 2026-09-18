"""Settlement-aware two-way refund mathematics for Phase 17.5."""

from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.arbitrage import evaluate_refundable_two_way_market
from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
)

NOW = datetime(2026, 9, 18, 1, 0, tzinfo=UTC)


def _quote(selection: str, price: str, index: int) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:refundable:{index}"),
        provider_id=ProviderId(f"provider:refundable:{index}"),
        event_id=EventId("event:refundable"),
        market_id=MarketId("market:refundable"),
        selection_id=SelectionId(selection),
        decimal_price=Decimal(price),
        source_event_id="source:event",
        source_market_id="source:market",
        source_selection_id=selection,
        ingested_at=NOW,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{index}",
    )


def test_refundable_two_way_positive_decisive_margin_has_zero_worst_case_profit() -> None:
    quotes = (
        _quote("selection:home", "2.10", 1),
        _quote("selection:away", "2.05", 2),
    )

    evaluation = evaluate_refundable_two_way_market(
        quotes,
        tuple(quote.selection_id for quote in quotes),
    )

    assert evaluation.implied_probability_sum < Decimal("1")
    assert evaluation.decisive_return_multiplier > Decimal("1")
    assert evaluation.decisive_profit_margin > Decimal("0")
    assert evaluation.refund_return_multiplier == Decimal("1")
    assert evaluation.worst_case_return_multiplier == Decimal("1")
    assert evaluation.worst_case_profit_margin == Decimal("0")
    assert evaluation.is_refundable_arbitrage
    assert not evaluation.has_strict_guaranteed_profit


def test_refundable_two_way_non_arbitrage_can_lose_in_decisive_state() -> None:
    quotes = (
        _quote("selection:home", "1.80", 1),
        _quote("selection:away", "1.80", 2),
    )

    evaluation = evaluate_refundable_two_way_market(
        quotes,
        tuple(quote.selection_id for quote in quotes),
    )

    assert evaluation.implied_probability_sum > Decimal("1")
    assert evaluation.decisive_return_multiplier < Decimal("1")
    assert evaluation.refund_return_multiplier == Decimal("1")
    assert evaluation.worst_case_return_multiplier == evaluation.decisive_return_multiplier
    assert evaluation.worst_case_profit_margin < Decimal("0")
    assert not evaluation.is_refundable_arbitrage
    assert not evaluation.has_strict_guaranteed_profit


def test_refundable_two_way_decisive_threshold_does_not_turn_refund_into_profit() -> None:
    quotes = (
        _quote("selection:home", "2.10", 1),
        _quote("selection:away", "2.05", 2),
    )

    accepted = evaluate_refundable_two_way_market(
        quotes,
        tuple(quote.selection_id for quote in quotes),
        minimum_decisive_profit_margin=Decimal("0.01"),
    )
    rejected = evaluate_refundable_two_way_market(
        quotes,
        tuple(quote.selection_id for quote in quotes),
        minimum_decisive_profit_margin=Decimal("0.03"),
    )

    assert accepted.is_refundable_arbitrage
    assert accepted.worst_case_profit_margin == Decimal("0")
    assert not rejected.is_refundable_arbitrage
    assert rejected.worst_case_profit_margin == Decimal("0")
