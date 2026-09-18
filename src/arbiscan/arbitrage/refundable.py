"""Settlement-aware mathematics for two-way markets with a shared refund state."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, localcontext

from arbiscan.arbitrage.core import MATH_PRECISION, evaluate_market
from arbiscan.arbitrage.errors import ArbitrageMathError
from arbiscan.arbitrage.models import RefundableTwoWayEvaluation
from arbiscan.domain import OddsQuote, SelectionId


def evaluate_refundable_two_way_market(
    quotes: Iterable[OddsQuote],
    expected_selection_ids: Iterable[SelectionId],
    *,
    minimum_decisive_profit_margin: Decimal = Decimal("0"),
) -> RefundableTwoWayEvaluation:
    """Evaluate two opposing prices when a third terminal state refunds both stakes.

    The ordinary reciprocal-odds calculation remains valid for the two decisive
    outcomes. The shared refund state always returns the total amount staked, so a
    positive decisive-state margin cannot become strictly positive guaranteed profit
    across all terminal states.
    """
    quote_values = tuple(quotes)
    expected_values = tuple(expected_selection_ids)
    if len(quote_values) != 2 or len(expected_values) != 2:
        raise ArbitrageMathError(
            "refundable two-way evaluation requires exactly two quotes and selections"
        )

    decisive = evaluate_market(
        quote_values,
        expected_values,
        minimum_profit_margin=minimum_decisive_profit_margin,
    )
    refund_return = Decimal("1")
    worst_return = min(decisive.return_multiplier, refund_return)
    with localcontext() as context:
        context.prec = MATH_PRECISION
        worst_margin = worst_return - Decimal("1")

    return RefundableTwoWayEvaluation(
        event_id=decisive.event_id,
        market_id=decisive.market_id,
        quotes=decisive.quotes,
        expected_selection_ids=decisive.expected_selection_ids,
        implied_probability_sum=decisive.implied_probability_sum,
        decisive_return_multiplier=decisive.return_multiplier,
        decisive_profit_margin=decisive.theoretical_profit_margin,
        refund_return_multiplier=refund_return,
        worst_case_return_multiplier=worst_return,
        worst_case_profit_margin=worst_margin,
        minimum_decisive_profit_margin=minimum_decisive_profit_margin,
        is_refundable_arbitrage=decisive.is_arbitrage,
        has_strict_guaranteed_profit=worst_margin > Decimal("0"),
    )
