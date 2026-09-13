"""Deterministic randomized property tests for the mathematics core."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, localcontext
from random import Random

from arbiscan.arbitrage import (
    CurrencyRoundingPolicy,
    allocate_stakes,
    build_opportunity,
    evaluate_market,
    implied_probability_sum,
    is_theoretical_arbitrage,
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
    StakePlanId,
)

NOW = datetime(2026, 9, 13, 14, 0, tzinfo=UTC)
EUR = CurrencyRoundingPolicy(currency="EUR", quantum=Decimal("0.01"))


def make_equal_odds_book(outcomes: int, odds: Decimal) -> tuple[OddsQuote, ...]:
    return tuple(
        OddsQuote(
            id=QuoteId(f"quote:{outcomes}:{index}"),
            provider_id=ProviderId(f"provider:{index}"),
            event_id=EventId(f"event:{outcomes}"),
            market_id=MarketId(f"market:{outcomes}"),
            selection_id=SelectionId(f"selection:{index:03d}"),
            decimal_price=odds,
            source_event_id=f"source-event:{outcomes}",
            source_market_id=f"source-market:{outcomes}",
            source_selection_id=f"source-selection:{index}",
            ingested_at=NOW,
            status=QuoteStatus.ACTIVE,
            trace_id=f"trace:{outcomes}:{index}",
        )
        for index in range(outcomes)
    )


def test_randomized_equal_odds_books_have_exact_boundary_classification() -> None:
    rng = Random(20260913)

    for _ in range(250):
        outcomes = rng.randint(2, 20)
        fair_odds = Decimal(outcomes)
        profitable_odds = Decimal(outcomes + rng.randint(1, 10))

        assert implied_probability_sum(tuple(fair_odds for _ in range(outcomes))) == Decimal("1")
        assert not is_theoretical_arbitrage(tuple(fair_odds for _ in range(outcomes)))
        assert is_theoretical_arbitrage(tuple(profitable_odds for _ in range(outcomes)))


def test_randomized_quote_order_does_not_change_evaluation() -> None:
    rng = Random(30031996)

    for outcomes in range(2, 12):
        quotes = list(make_equal_odds_book(outcomes, Decimal(outcomes + 1)))
        expected = tuple(quote.selection_id for quote in quotes)
        baseline = evaluate_market(quotes, expected)

        rng.shuffle(quotes)
        shuffled = evaluate_market(quotes, reversed(expected))

        assert shuffled.implied_probability_sum == baseline.implied_probability_sum
        assert shuffled.return_multiplier == baseline.return_multiplier
        assert shuffled.theoretical_profit_margin == baseline.theoretical_profit_margin
        assert shuffled.quotes == baseline.quotes


def test_external_decimal_context_does_not_change_evaluation_metrics() -> None:
    quotes = make_equal_odds_book(3, Decimal("4"))
    expected = tuple(quote.selection_id for quote in quotes)
    baseline = evaluate_market(quotes, expected)

    with localcontext() as external_context:
        external_context.prec = 7
        constrained = evaluate_market(quotes, expected)

    assert constrained.implied_probability_sum == baseline.implied_probability_sum
    assert constrained.return_multiplier == baseline.return_multiplier
    assert constrained.theoretical_profit_margin == baseline.theoretical_profit_margin
    assert constrained.is_arbitrage == baseline.is_arbitrage


def test_randomized_profitable_books_produce_positive_conservative_stake_plans() -> None:
    rng = Random(424242)

    for case in range(100):
        outcomes = rng.randint(2, 8)
        odds = Decimal(outcomes + rng.randint(1, 4))
        quotes = make_equal_odds_book(outcomes, odds)
        evaluation = evaluate_market(quotes, tuple(quote.selection_id for quote in quotes))
        opportunity = build_opportunity(
            evaluation,
            opportunity_id=OpportunityId(f"opportunity:{case}"),
            detected_at=NOW,
        )
        bankroll = Decimal(rng.randint(50, 500))

        plan = allocate_stakes(
            opportunity,
            quotes,
            bankroll=bankroll,
            stake_plan_id=StakePlanId(f"stake-plan:{case}"),
            created_at=NOW,
            rounding_policy=EUR,
        )

        assert plan is not None
        total_staked = sum((allocation.amount for allocation in plan.allocations), Decimal("0"))
        payouts = [allocation.expected_payout for allocation in plan.allocations]
        assert total_staked <= bankroll
        assert plan.guaranteed_payout == min(payouts)
        assert plan.guaranteed_profit == plan.guaranteed_payout - total_staked
        assert plan.guaranteed_profit > Decimal("0")
        assert max(payouts) - min(payouts) <= odds * EUR.quantum + EUR.quantum
