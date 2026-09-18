"""Immutable value objects used by the pure arbitrage mathematics core."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from arbiscan.arbitrage.errors import ArbitrageMathError, StakeConstraintError
from arbiscan.domain import EventId, MarketId, OddsQuote, QuoteId, SelectionId

_EVALUATION_CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)


def _require_decimal(value: object, *, field: str) -> Decimal:
    if type(value) is not Decimal:
        raise ArbitrageMathError(f"{field} must be Decimal")
    if not value.is_finite():
        raise ArbitrageMathError(f"{field} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class ArbitrageEvaluation:
    """Deterministic evaluation of one complete canonical market book."""

    event_id: EventId
    market_id: MarketId
    quotes: tuple[OddsQuote, ...]
    expected_selection_ids: tuple[SelectionId, ...]
    implied_probability_sum: Decimal
    return_multiplier: Decimal
    theoretical_profit_margin: Decimal
    minimum_profit_margin: Decimal
    is_arbitrage: bool

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId):
            raise ArbitrageMathError("evaluation.event_id must be EventId")
        if not isinstance(self.market_id, MarketId):
            raise ArbitrageMathError("evaluation.market_id must be MarketId")

        quotes = tuple(self.quotes)
        expected = tuple(self.expected_selection_ids)
        object.__setattr__(self, "quotes", quotes)
        object.__setattr__(self, "expected_selection_ids", expected)

        if len(quotes) < 2:
            raise ArbitrageMathError("evaluation requires at least two quotes")
        if len(expected) < 2:
            raise ArbitrageMathError("evaluation requires at least two expected selections")
        if len(set(expected)) != len(expected):
            raise ArbitrageMathError("expected selection IDs must be unique")
        if any(not isinstance(selection_id, SelectionId) for selection_id in expected):
            raise ArbitrageMathError("expected selections must contain SelectionId values")
        if any(not isinstance(quote, OddsQuote) for quote in quotes):
            raise ArbitrageMathError("evaluation quotes must contain OddsQuote values")
        if any(quote.event_id != self.event_id for quote in quotes):
            raise ArbitrageMathError("all evaluation quotes must belong to the same event")
        if any(quote.market_id != self.market_id for quote in quotes):
            raise ArbitrageMathError("all evaluation quotes must belong to the same market")

        quote_ids = [quote.id for quote in quotes]
        if len(set(quote_ids)) != len(quote_ids):
            raise ArbitrageMathError("evaluation quote IDs must be unique")
        selection_ids = [quote.selection_id for quote in quotes]
        if len(set(selection_ids)) != len(selection_ids):
            raise ArbitrageMathError("evaluation selection IDs must be unique")
        if set(selection_ids) != set(expected):
            raise ArbitrageMathError("evaluation quotes must cover exactly the expected selections")

        implied_sum = _require_decimal(
            self.implied_probability_sum,
            field="evaluation.implied_probability_sum",
        )
        return_multiplier = _require_decimal(
            self.return_multiplier,
            field="evaluation.return_multiplier",
        )
        margin = _require_decimal(
            self.theoretical_profit_margin,
            field="evaluation.theoretical_profit_margin",
        )
        threshold = _require_decimal(
            self.minimum_profit_margin,
            field="evaluation.minimum_profit_margin",
        )
        if implied_sum <= Decimal("0"):
            raise ArbitrageMathError("implied probability sum must be positive")
        if return_multiplier <= Decimal("0"):
            raise ArbitrageMathError("return multiplier must be positive")
        if threshold < Decimal("0"):
            raise ArbitrageMathError("minimum profit margin cannot be negative")

        with localcontext(_EVALUATION_CONTEXT):
            expected_margin = return_multiplier - Decimal("1")
        if margin != expected_margin:
            raise ArbitrageMathError("profit margin must equal return multiplier minus one")

        expected_flag = implied_sum < Decimal("1") and margin > Decimal("0") and margin >= threshold
        if self.is_arbitrage is not expected_flag:
            raise ArbitrageMathError("evaluation arbitrage flag is inconsistent with its metrics")


@dataclass(frozen=True, slots=True)
class RefundableTwoWayEvaluation:
    """Settlement-aware evaluation for a two-way market with a shared refund state."""

    event_id: EventId
    market_id: MarketId
    quotes: tuple[OddsQuote, ...]
    expected_selection_ids: tuple[SelectionId, ...]
    implied_probability_sum: Decimal
    decisive_return_multiplier: Decimal
    decisive_profit_margin: Decimal
    refund_return_multiplier: Decimal
    worst_case_return_multiplier: Decimal
    worst_case_profit_margin: Decimal
    minimum_decisive_profit_margin: Decimal
    is_refundable_arbitrage: bool
    has_strict_guaranteed_profit: bool

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId):
            raise ArbitrageMathError("refundable evaluation.event_id must be EventId")
        if not isinstance(self.market_id, MarketId):
            raise ArbitrageMathError("refundable evaluation.market_id must be MarketId")

        quotes = tuple(self.quotes)
        expected = tuple(self.expected_selection_ids)
        object.__setattr__(self, "quotes", quotes)
        object.__setattr__(self, "expected_selection_ids", expected)

        if len(quotes) != 2 or len(expected) != 2:
            raise ArbitrageMathError(
                "refundable two-way evaluation requires exactly two quotes and selections"
            )
        if any(not isinstance(quote, OddsQuote) for quote in quotes):
            raise ArbitrageMathError("refundable evaluation quotes must contain OddsQuote values")
        if any(not isinstance(selection_id, SelectionId) for selection_id in expected):
            raise ArbitrageMathError(
                "refundable expected selections must contain SelectionId values"
            )
        if len(set(expected)) != 2:
            raise ArbitrageMathError("refundable expected selection IDs must be unique")
        if any(quote.event_id != self.event_id for quote in quotes):
            raise ArbitrageMathError("refundable quotes must belong to the same event")
        if any(quote.market_id != self.market_id for quote in quotes):
            raise ArbitrageMathError("refundable quotes must belong to the same market")
        if len({quote.id for quote in quotes}) != 2:
            raise ArbitrageMathError("refundable evaluation quote IDs must be unique")
        if {quote.selection_id for quote in quotes} != set(expected):
            raise ArbitrageMathError("refundable quotes must cover exactly the expected selections")

        implied_sum = _require_decimal(
            self.implied_probability_sum,
            field="refundable_evaluation.implied_probability_sum",
        )
        decisive_return = _require_decimal(
            self.decisive_return_multiplier,
            field="refundable_evaluation.decisive_return_multiplier",
        )
        decisive_margin = _require_decimal(
            self.decisive_profit_margin,
            field="refundable_evaluation.decisive_profit_margin",
        )
        refund_return = _require_decimal(
            self.refund_return_multiplier,
            field="refundable_evaluation.refund_return_multiplier",
        )
        worst_return = _require_decimal(
            self.worst_case_return_multiplier,
            field="refundable_evaluation.worst_case_return_multiplier",
        )
        worst_margin = _require_decimal(
            self.worst_case_profit_margin,
            field="refundable_evaluation.worst_case_profit_margin",
        )
        threshold = _require_decimal(
            self.minimum_decisive_profit_margin,
            field="refundable_evaluation.minimum_decisive_profit_margin",
        )

        if implied_sum <= Decimal("0"):
            raise ArbitrageMathError("refundable implied probability sum must be positive")
        if decisive_return <= Decimal("0"):
            raise ArbitrageMathError("decisive return multiplier must be positive")
        if refund_return != Decimal("1"):
            raise ArbitrageMathError("shared refund return multiplier must equal one")
        if threshold < Decimal("0"):
            raise ArbitrageMathError("minimum decisive profit margin cannot be negative")

        with localcontext(_EVALUATION_CONTEXT):
            if decisive_margin != decisive_return - Decimal("1"):
                raise ArbitrageMathError(
                    "decisive profit margin must equal decisive return multiplier minus one"
                )
            expected_worst_return = min(decisive_return, refund_return)
            expected_worst_margin = expected_worst_return - Decimal("1")

        if worst_return != expected_worst_return:
            raise ArbitrageMathError(
                "worst-case return multiplier must include the shared refund state"
            )
        if worst_margin != expected_worst_margin:
            raise ArbitrageMathError(
                "worst-case profit margin must equal worst-case return minus one"
            )

        expected_refundable = (
            implied_sum < Decimal("1")
            and decisive_margin > Decimal("0")
            and decisive_margin >= threshold
            and refund_return >= Decimal("1")
        )
        if self.is_refundable_arbitrage is not expected_refundable:
            raise ArbitrageMathError(
                "refundable arbitrage flag is inconsistent with settlement metrics"
            )

        expected_strict = worst_margin > Decimal("0")
        if self.has_strict_guaranteed_profit is not expected_strict:
            raise ArbitrageMathError(
                "strict guaranteed-profit flag is inconsistent with worst-case settlement"
            )


@dataclass(frozen=True, slots=True)
class StakeConstraint:
    """Per-quote bookmaker stake limits interpreted on a zero-based increment grid."""

    quote_id: QuoteId
    minimum_stake: Decimal = Decimal("0")
    maximum_stake: Decimal | None = None
    stake_increment: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        if not isinstance(self.quote_id, QuoteId):
            raise StakeConstraintError("stake_constraint.quote_id must be QuoteId")

        minimum = _require_decimal(self.minimum_stake, field="stake_constraint.minimum_stake")
        increment = _require_decimal(self.stake_increment, field="stake_constraint.stake_increment")
        if minimum < Decimal("0"):
            raise StakeConstraintError("minimum stake cannot be negative")
        if increment <= Decimal("0"):
            raise StakeConstraintError("stake increment must be positive")

        if self.maximum_stake is not None:
            maximum = _require_decimal(
                self.maximum_stake,
                field="stake_constraint.maximum_stake",
            )
            if maximum <= Decimal("0"):
                raise StakeConstraintError("maximum stake must be positive")
            if maximum < minimum:
                raise StakeConstraintError("maximum stake cannot be below minimum stake")


@dataclass(frozen=True, slots=True)
class CurrencyRoundingPolicy:
    """Currency quantum used for conservative payout rounding."""

    currency: str
    quantum: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        if not isinstance(self.currency, str):
            raise StakeConstraintError("rounding policy currency must be a string")
        currency = self.currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise StakeConstraintError("rounding policy currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)

        quantum = _require_decimal(self.quantum, field="rounding_policy.quantum")
        if quantum <= Decimal("0"):
            raise StakeConstraintError("currency quantum must be positive")
