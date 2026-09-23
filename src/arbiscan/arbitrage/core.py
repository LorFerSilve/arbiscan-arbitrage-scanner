"""Pure provider-independent arbitrage detection mathematics."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from fractions import Fraction

from arbiscan.arbitrage.errors import ArbitrageMathError, IncompleteMarketError
from arbiscan.arbitrage.models import ArbitrageEvaluation
from arbiscan.domain import (
    OddsQuote,
    Opportunity,
    OpportunityId,
    QuoteStatus,
    SelectionId,
)

MATH_PRECISION = 60
_MATH_CONTEXT = Context(prec=MATH_PRECISION, rounding=ROUND_HALF_EVEN)
_ONE = Decimal("1")
_ZERO = Decimal("0")


def _require_decimal(value: object, *, field: str) -> Decimal:
    if type(value) is not Decimal:
        raise ArbitrageMathError(f"{field} must be Decimal")
    if not value.is_finite():
        raise ArbitrageMathError(f"{field} must be finite")
    return value


def _validate_odds(odds: object, *, field: str = "odds") -> Decimal:
    value = _require_decimal(odds, field=field)
    if value <= _ONE:
        raise ArbitrageMathError(f"{field} must be greater than 1")
    return value


def _as_fraction(value: Decimal) -> Fraction:
    numerator, denominator = value.as_integer_ratio()
    return Fraction(numerator, denominator)


def _fraction_to_decimal(value: Fraction) -> Decimal:
    with localcontext(_MATH_CONTEXT):
        return Decimal(value.numerator) / Decimal(value.denominator)


def _exact_implied_sum(odds: Iterable[Decimal]) -> Fraction:
    values = tuple(odds)
    if len(values) < 2:
        raise ArbitrageMathError("an arbitrage book requires at least two outcomes")

    total = Fraction(0, 1)
    for index, raw_odds in enumerate(values):
        decimal_odds = _validate_odds(raw_odds, field=f"odds[{index}]")
        total += Fraction(1, 1) / _as_fraction(decimal_odds)
    return total


def implied_probability(odds: Decimal) -> Decimal:
    """Return the implied probability for one decimal price."""
    decimal_odds = _validate_odds(odds)
    return _fraction_to_decimal(Fraction(1, 1) / _as_fraction(decimal_odds))


def implied_probability_sum(odds: Iterable[Decimal]) -> Decimal:
    """Return the implied probability sum for a complete outcome book."""
    return _fraction_to_decimal(_exact_implied_sum(odds))


def gross_return_multiplier(odds: Iterable[Decimal]) -> Decimal:
    """Return the equalized theoretical gross return multiplier ``1 / S``."""
    implied_sum = _exact_implied_sum(odds)
    return _fraction_to_decimal(Fraction(1, 1) / implied_sum)


def theoretical_profit_margin(odds: Iterable[Decimal]) -> Decimal:
    """Return the gross theoretical profit margin ``(1 / S) - 1``."""
    values = tuple(odds)
    with localcontext(_MATH_CONTEXT):
        return gross_return_multiplier(values) - _ONE


def is_theoretical_arbitrage(
    odds: Iterable[Decimal],
    *,
    minimum_profit_margin: Decimal = Decimal("0"),
) -> bool:
    """Return whether a complete book is an arbitrage above the configured threshold."""
    threshold = _require_decimal(minimum_profit_margin, field="minimum_profit_margin")
    if threshold < _ZERO:
        raise ArbitrageMathError("minimum profit margin cannot be negative")

    values = tuple(odds)
    exact_sum = _exact_implied_sum(values)
    if exact_sum >= Fraction(1, 1):
        return False

    margin = theoretical_profit_margin(values)
    return margin > _ZERO and margin >= threshold


def evaluate_market(
    quotes: Iterable[OddsQuote],
    expected_selection_ids: Iterable[SelectionId],
    *,
    minimum_profit_margin: Decimal = Decimal("0"),
) -> ArbitrageEvaluation:
    """Validate and evaluate one complete canonical market book.

    The function deliberately does not choose the best quote per selection; that
    responsibility belongs to the later market-book construction phase. Phase 3
    requires callers to provide exactly one active quote for each expected
    canonical selection.
    """
    quote_values = tuple(quotes)
    expected_values = tuple(expected_selection_ids)

    if len(quote_values) < 2:
        raise ArbitrageMathError("market evaluation requires at least two quotes")
    if len(expected_values) < 2:
        raise ArbitrageMathError("market evaluation requires at least two expected selections")
    if any(not isinstance(quote, OddsQuote) for quote in quote_values):
        raise ArbitrageMathError("market evaluation only accepts OddsQuote values")
    if any(not isinstance(selection_id, SelectionId) for selection_id in expected_values):
        raise ArbitrageMathError("expected selections must contain SelectionId values")
    if len(set(expected_values)) != len(expected_values):
        raise ArbitrageMathError("expected selection IDs must be unique")

    first = quote_values[0]
    if any(quote.event_id != first.event_id for quote in quote_values):
        raise ArbitrageMathError("all quotes must belong to the same canonical event")
    if any(quote.market_id != first.market_id for quote in quote_values):
        raise ArbitrageMathError("all quotes must belong to the same canonical market")
    if any(quote.status is not QuoteStatus.ACTIVE for quote in quote_values):
        raise ArbitrageMathError("only active quotes are eligible for arbitrage evaluation")

    quote_ids = [quote.id for quote in quote_values]
    if len(set(quote_ids)) != len(quote_ids):
        raise ArbitrageMathError("quote IDs must be unique within a market evaluation")

    actual_selection_ids = [quote.selection_id for quote in quote_values]
    if len(set(actual_selection_ids)) != len(actual_selection_ids):
        raise ArbitrageMathError("duplicate selections are not allowed in a market evaluation")

    actual_set = set(actual_selection_ids)
    expected_set = set(expected_values)
    if actual_set != expected_set:
        missing = sorted(selection_id.value for selection_id in expected_set - actual_set)
        unexpected = sorted(selection_id.value for selection_id in actual_set - expected_set)
        raise IncompleteMarketError(
            f"market selections do not match expected outcomes; missing={missing}, "
            f"unexpected={unexpected}"
        )

    ordered_quotes = tuple(sorted(quote_values, key=lambda quote: quote.selection_id.value))
    ordered_expected = tuple(sorted(expected_values, key=lambda selection_id: selection_id.value))
    odds = tuple(quote.decimal_price for quote in ordered_quotes)
    # Exact rational arithmetic is the expensive part of an evaluation. Reuse the
    # same exact sum for all reported fields and the threshold decision.
    exact_sum = _exact_implied_sum(odds)
    implied_sum = _fraction_to_decimal(exact_sum)
    return_multiplier = _fraction_to_decimal(Fraction(1, 1) / exact_sum)
    with localcontext(_MATH_CONTEXT):
        margin = return_multiplier - _ONE

    threshold = _require_decimal(minimum_profit_margin, field="minimum_profit_margin")
    if threshold < _ZERO:
        raise ArbitrageMathError("minimum profit margin cannot be negative")
    arbitrage = exact_sum < Fraction(1, 1) and margin > _ZERO and margin >= threshold

    return ArbitrageEvaluation(
        event_id=first.event_id,
        market_id=first.market_id,
        quotes=ordered_quotes,
        expected_selection_ids=ordered_expected,
        implied_probability_sum=implied_sum,
        return_multiplier=return_multiplier,
        theoretical_profit_margin=margin,
        minimum_profit_margin=threshold,
        is_arbitrage=arbitrage,
    )


def build_opportunity(
    evaluation: ArbitrageEvaluation,
    *,
    opportunity_id: OpportunityId,
    detected_at: datetime,
) -> Opportunity:
    """Materialize a canonical Opportunity from a positive deterministic evaluation."""
    if not isinstance(evaluation, ArbitrageEvaluation):
        raise ArbitrageMathError("evaluation must be ArbitrageEvaluation")
    if not evaluation.is_arbitrage:
        raise ArbitrageMathError("cannot build an opportunity from a non-arbitrage evaluation")

    return Opportunity(
        id=opportunity_id,
        event_id=evaluation.event_id,
        market_id=evaluation.market_id,
        quote_ids=tuple(quote.id for quote in evaluation.quotes),
        implied_probability_sum=evaluation.implied_probability_sum,
        theoretical_profit_margin=evaluation.theoretical_profit_margin,
        detected_at=detected_at,
    )
