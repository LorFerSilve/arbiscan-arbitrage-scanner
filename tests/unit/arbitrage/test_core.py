"""Deterministic examples and validation tests for arbitrage detection."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from arbiscan.arbitrage import (
    ArbitrageMathError,
    IncompleteMarketError,
    build_opportunity,
    evaluate_market,
    gross_return_multiplier,
    implied_probability,
    implied_probability_sum,
    is_theoretical_arbitrage,
    theoretical_profit_margin,
)
from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    OpportunityId,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
)

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def make_quote(
    selection: str,
    odds: str,
    *,
    index: int,
    event: str = "event:1",
    market: str = "market:1",
    status: QuoteStatus = QuoteStatus.ACTIVE,
) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:{index}"),
        provider_id=ProviderId(f"provider:{index}"),
        event_id=EventId(event),
        market_id=MarketId(market),
        selection_id=SelectionId(selection),
        decimal_price=Decimal(odds),
        source_event_id=f"source-event:{index}",
        source_market_id=f"source-market:{index}",
        source_selection_id=selection,
        ingested_at=NOW,
        status=status,
        trace_id=f"trace:{index}",
    )


def test_basic_probability_and_margin_formulae() -> None:
    odds = (Decimal("2.20"), Decimal("2.20"))

    assert implied_probability(Decimal("2")) == Decimal("0.5")
    assert implied_probability_sum((Decimal("2"), Decimal("2"))) == Decimal("1")
    assert gross_return_multiplier(odds) > Decimal("1")
    assert theoretical_profit_margin(odds) == gross_return_multiplier(odds) - Decimal("1")
    assert is_theoretical_arbitrage(odds)


def test_exact_fair_three_way_book_is_not_misclassified_by_repeating_thirds() -> None:
    odds = (Decimal("3"), Decimal("3"), Decimal("3"))

    assert implied_probability_sum(odds) == Decimal("1")
    assert not is_theoretical_arbitrage(odds)


def test_three_way_football_and_arbitrary_n_outcome_books_are_supported() -> None:
    assert is_theoretical_arbitrage(
        (Decimal("3.60"), Decimal("3.60"), Decimal("3.60"))
    )
    assert is_theoretical_arbitrage(tuple(Decimal("8") for _ in range(7)))


def test_invalid_odds_and_binary_float_inputs_fail_closed() -> None:
    with pytest.raises(ArbitrageMathError):
        implied_probability(Decimal("1"))
    with pytest.raises(ArbitrageMathError):
        implied_probability(Decimal("0"))
    with pytest.raises(ArbitrageMathError):
        implied_probability(2.0)  # type: ignore[arg-type]


def test_minimum_profit_threshold_is_respected() -> None:
    odds = (Decimal("2.10"), Decimal("2.10"))

    assert is_theoretical_arbitrage(odds, minimum_profit_margin=Decimal("0.04"))
    assert not is_theoretical_arbitrage(odds, minimum_profit_margin=Decimal("0.06"))


def test_evaluation_is_order_independent_and_builds_canonical_opportunity() -> None:
    quotes = (
        make_quote("selection:b", "2.20", index=2),
        make_quote("selection:a", "2.20", index=1),
    )
    expected = (SelectionId("selection:a"), SelectionId("selection:b"))

    evaluation = evaluate_market(quotes, expected)
    opportunity = build_opportunity(
        evaluation,
        opportunity_id=OpportunityId("opportunity:1"),
        detected_at=NOW,
    )

    assert evaluation.is_arbitrage
    assert [quote.selection_id.value for quote in evaluation.quotes] == [
        "selection:a",
        "selection:b",
    ]
    assert opportunity.quote_ids == tuple(quote.id for quote in evaluation.quotes)
    assert opportunity.implied_probability_sum == evaluation.implied_probability_sum
    assert opportunity.theoretical_profit_margin == evaluation.theoretical_profit_margin


def test_duplicate_selection_is_rejected() -> None:
    quotes = (
        make_quote("selection:a", "2.20", index=1),
        make_quote("selection:a", "2.30", index=2),
    )

    with pytest.raises(ArbitrageMathError, match="duplicate selections"):
        evaluate_market(quotes, (SelectionId("selection:a"), SelectionId("selection:b")))


def test_incomplete_market_is_rejected() -> None:
    quotes = (
        make_quote("selection:a", "3.60", index=1),
        make_quote("selection:b", "3.60", index=2),
    )
    expected = (
        SelectionId("selection:a"),
        SelectionId("selection:b"),
        SelectionId("selection:draw"),
    )

    with pytest.raises(IncompleteMarketError, match="missing"):
        evaluate_market(quotes, expected)


def test_cross_event_cross_market_and_suspended_quotes_are_rejected() -> None:
    expected = (SelectionId("selection:a"), SelectionId("selection:b"))

    with pytest.raises(ArbitrageMathError, match="same canonical event"):
        evaluate_market(
            (
                make_quote("selection:a", "2.20", index=1, event="event:a"),
                make_quote("selection:b", "2.20", index=2, event="event:b"),
            ),
            expected,
        )

    with pytest.raises(ArbitrageMathError, match="same canonical market"):
        evaluate_market(
            (
                make_quote("selection:a", "2.20", index=1, market="market:a"),
                make_quote("selection:b", "2.20", index=2, market="market:b"),
            ),
            expected,
        )

    with pytest.raises(ArbitrageMathError, match="active quotes"):
        evaluate_market(
            (
                make_quote("selection:a", "2.20", index=1),
                make_quote(
                    "selection:b",
                    "2.20",
                    index=2,
                    status=QuoteStatus.SUSPENDED,
                ),
            ),
            expected,
        )
