"""Deterministic stake allocation with conservative monetary rounding."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext

from arbiscan.arbitrage.core import (
    MATH_PRECISION,
    implied_probability_sum,
    theoretical_profit_margin,
)
from arbiscan.arbitrage.errors import ArbitrageMathError, StakeConstraintError
from arbiscan.arbitrage.models import CurrencyRoundingPolicy, StakeConstraint
from arbiscan.domain import (
    OddsQuote,
    Opportunity,
    OpportunityStatus,
    QuoteId,
    QuoteStatus,
    StakeAllocation,
    StakePlan,
    StakePlanId,
)

_MATH_CONTEXT = Context(prec=MATH_PRECISION, rounding=ROUND_HALF_EVEN)
_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class _EffectiveConstraint:
    minimum: Decimal
    maximum: Decimal | None
    increment: Decimal


def _require_decimal(value: object, *, field: str) -> Decimal:
    if type(value) is not Decimal:
        raise ArbitrageMathError(f"{field} must be Decimal")
    if not value.is_finite():
        raise ArbitrageMathError(f"{field} must be finite")
    return value


def _floor_to_grid(value: Decimal, step: Decimal) -> Decimal:
    with localcontext(_MATH_CONTEXT):
        units = (value / step).to_integral_value(rounding=ROUND_FLOOR)
        return units * step


def _ceil_to_grid(value: Decimal, step: Decimal) -> Decimal:
    with localcontext(_MATH_CONTEXT):
        units = (value / step).to_integral_value(rounding=ROUND_CEILING)
        return units * step


def _conservative_payout(stake: Decimal, odds: Decimal, quantum: Decimal) -> Decimal:
    with localcontext(_MATH_CONTEXT):
        return _floor_to_grid(stake * odds, quantum)


def _effective_constraints(
    quotes: tuple[OddsQuote, ...],
    constraints: Iterable[StakeConstraint],
    policy: CurrencyRoundingPolicy,
) -> tuple[_EffectiveConstraint, ...] | None:
    provided: dict[QuoteId, StakeConstraint] = {}
    quote_ids = {quote.id for quote in quotes}
    for constraint in constraints:
        if not isinstance(constraint, StakeConstraint):
            raise StakeConstraintError("constraints must contain StakeConstraint values")
        if constraint.quote_id not in quote_ids:
            raise StakeConstraintError(
                "stake constraint references a quote outside the opportunity"
            )
        if constraint.quote_id in provided:
            raise StakeConstraintError("duplicate stake constraint for quote")
        provided[constraint.quote_id] = constraint

    effective: list[_EffectiveConstraint] = []
    for quote in quotes:
        constraint = provided.get(
            quote.id,
            StakeConstraint(quote_id=quote.id, stake_increment=policy.quantum),
        )
        increment = constraint.stake_increment
        with localcontext(_MATH_CONTEXT):
            if increment % policy.quantum != _ZERO:
                raise StakeConstraintError(
                    "stake increments must be exact multiples of the currency quantum"
                )

        minimum = max(increment, _ceil_to_grid(constraint.minimum_stake, increment))
        maximum: Decimal | None = None
        if constraint.maximum_stake is not None:
            maximum = _floor_to_grid(constraint.maximum_stake, increment)
            if maximum < minimum:
                return None

        effective.append(
            _EffectiveConstraint(
                minimum=minimum,
                maximum=maximum,
                increment=increment,
            )
        )
    return tuple(effective)


def _continuous_target_payout(
    quotes: tuple[OddsQuote, ...],
    constraints: tuple[_EffectiveConstraint, ...],
    bankroll: Decimal,
) -> Decimal | None:
    with localcontext(_MATH_CONTEXT):
        minimum_total = sum((constraint.minimum for constraint in constraints), _ZERO)
        if minimum_total > bankroll:
            return None

        active = set(range(len(quotes)))
        fixed = _ZERO
        target: Decimal | None = None

        while active:
            reciprocal_sum = sum(
                (Decimal("1") / quotes[index].decimal_price for index in active),
                _ZERO,
            )
            if reciprocal_sum <= _ZERO:
                raise ArbitrageMathError("invalid reciprocal sum during stake allocation")
            target = (bankroll - fixed) / reciprocal_sum

            violating = {
                index
                for index in active
                if target / quotes[index].decimal_price < constraints[index].minimum
            }
            if not violating:
                break
            for index in violating:
                fixed += constraints[index].minimum
                active.remove(index)
            if fixed > bankroll:
                return None

        if target is None:
            target = min(
                constraint.minimum * quote.decimal_price
                for quote, constraint in zip(quotes, constraints, strict=True)
            )

        maximum_payouts = [
            constraint.maximum * quote.decimal_price
            for quote, constraint in zip(quotes, constraints, strict=True)
            if constraint.maximum is not None
        ]
        if maximum_payouts:
            target = min(target, min(maximum_payouts))
        return target


def _candidate_amounts(
    quotes: tuple[OddsQuote, ...],
    constraints: tuple[_EffectiveConstraint, ...],
    target_payout: Decimal,
) -> tuple[tuple[Decimal, ...], ...] | None:
    candidates: list[tuple[Decimal, ...]] = []
    for quote, constraint in zip(quotes, constraints, strict=True):
        with localcontext(_MATH_CONTEXT):
            raw = max(constraint.minimum, target_payout / quote.decimal_price)
            low = max(constraint.minimum, _floor_to_grid(raw, constraint.increment))
            high = max(constraint.minimum, _ceil_to_grid(raw, constraint.increment))

        if constraint.maximum is not None:
            if low > constraint.maximum:
                return None
            high = min(high, constraint.maximum)
        if high < low:
            high = low

        values = (low,) if high == low else (low, high)
        candidates.append(values)
    return tuple(candidates)


def _select_best_rounded_amounts(
    quotes: tuple[OddsQuote, ...],
    candidates: tuple[tuple[Decimal, ...], ...],
    bankroll: Decimal,
    quantum: Decimal,
) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...], Decimal, Decimal] | None:
    payout_candidates = sorted(
        {
            _conservative_payout(amount, quote.decimal_price, quantum)
            for quote, amounts in zip(quotes, candidates, strict=True)
            for amount in amounts
        }
    )

    best: tuple[Decimal, Decimal, Decimal, tuple[Decimal, ...], tuple[Decimal, ...]] | None = None
    for target_payout in payout_candidates:
        selected: list[Decimal] = []
        payouts: list[Decimal] = []
        feasible = True

        for quote, amounts in zip(quotes, candidates, strict=True):
            options = [
                (amount, _conservative_payout(amount, quote.decimal_price, quantum))
                for amount in amounts
            ]
            qualifying = [option for option in options if option[1] >= target_payout]
            if not qualifying:
                feasible = False
                break
            amount, payout = min(qualifying, key=lambda option: option[0])
            selected.append(amount)
            payouts.append(payout)

        if not feasible:
            continue

        with localcontext(_MATH_CONTEXT):
            total_staked = sum(selected, _ZERO)
            if total_staked > bankroll:
                continue
            guaranteed_payout = min(payouts)
            guaranteed_profit = guaranteed_payout - total_staked
            key = (
                guaranteed_profit,
                guaranteed_payout,
                -total_staked,
                tuple(selected),
                tuple(payouts),
            )
        if best is None or key > best:
            best = key

    if best is None:
        return None
    guaranteed_profit, guaranteed_payout, _negative_total, selected_tuple, payouts_tuple = best
    return selected_tuple, payouts_tuple, guaranteed_payout, guaranteed_profit


def allocate_stakes(
    opportunity: Opportunity,
    quotes: Iterable[OddsQuote],
    *,
    bankroll: Decimal,
    stake_plan_id: StakePlanId,
    created_at: datetime,
    rounding_policy: CurrencyRoundingPolicy,
    constraints: Iterable[StakeConstraint] = (),
    minimum_guaranteed_profit: Decimal = Decimal("0"),
) -> StakePlan | None:
    """Build a conservative executable stake plan or return ``None`` if none is safe.

    Returned payouts are rounded down to the currency quantum. A plan is only
    materialized when its post-rounding guaranteed profit is strictly positive
    and meets ``minimum_guaranteed_profit``.
    """
    if not isinstance(opportunity, Opportunity):
        raise ArbitrageMathError("opportunity must be Opportunity")
    if opportunity.status is not OpportunityStatus.ACTIVE:
        raise ArbitrageMathError("only active opportunities can be allocated")
    if not isinstance(rounding_policy, CurrencyRoundingPolicy):
        raise StakeConstraintError("rounding_policy must be CurrencyRoundingPolicy")

    bankroll_value = _require_decimal(bankroll, field="bankroll")
    if bankroll_value <= _ZERO:
        raise ArbitrageMathError("bankroll must be positive")
    profit_threshold = _require_decimal(
        minimum_guaranteed_profit,
        field="minimum_guaranteed_profit",
    )
    if profit_threshold < _ZERO:
        raise ArbitrageMathError("minimum guaranteed profit cannot be negative")

    quote_values = tuple(quotes)
    if len(quote_values) < 2:
        raise ArbitrageMathError("stake allocation requires at least two quotes")
    if any(not isinstance(quote, OddsQuote) for quote in quote_values):
        raise ArbitrageMathError("stake allocation only accepts OddsQuote values")
    if any(quote.status is not QuoteStatus.ACTIVE for quote in quote_values):
        raise ArbitrageMathError("stake allocation only accepts active quotes")
    if any(quote.event_id != opportunity.event_id for quote in quote_values):
        raise ArbitrageMathError("stake quotes must belong to the opportunity event")
    if any(quote.market_id != opportunity.market_id for quote in quote_values):
        raise ArbitrageMathError("stake quotes must belong to the opportunity market")

    quote_ids = [quote.id for quote in quote_values]
    if len(set(quote_ids)) != len(quote_ids):
        raise ArbitrageMathError("stake quote IDs must be unique")
    selection_ids = [quote.selection_id for quote in quote_values]
    if len(set(selection_ids)) != len(selection_ids):
        raise ArbitrageMathError("stake quote selections must be unique")
    if set(quote_ids) != set(opportunity.quote_ids):
        raise ArbitrageMathError("stake quotes must exactly match opportunity quote IDs")

    ordered_quotes = tuple(sorted(quote_values, key=lambda quote: quote.selection_id.value))
    odds = tuple(quote.decimal_price for quote in ordered_quotes)
    if implied_probability_sum(odds) != opportunity.implied_probability_sum:
        raise ArbitrageMathError("opportunity implied probability sum does not match its quotes")
    if theoretical_profit_margin(odds) != opportunity.theoretical_profit_margin:
        raise ArbitrageMathError("opportunity profit margin does not match its quotes")

    effective = _effective_constraints(ordered_quotes, constraints, rounding_policy)
    if effective is None:
        return None
    target_payout = _continuous_target_payout(ordered_quotes, effective, bankroll_value)
    if target_payout is None:
        return None
    candidates = _candidate_amounts(ordered_quotes, effective, target_payout)
    if candidates is None:
        return None

    selected = _select_best_rounded_amounts(
        ordered_quotes,
        candidates,
        bankroll_value,
        rounding_policy.quantum,
    )
    if selected is None:
        return None
    amounts, payouts, guaranteed_payout, guaranteed_profit = selected
    if guaranteed_profit <= _ZERO or guaranteed_profit < profit_threshold:
        return None

    allocations = tuple(
        StakeAllocation(
            quote_id=quote.id,
            selection_id=quote.selection_id,
            provider_id=quote.provider_id,
            amount=amount,
            expected_payout=payout,
        )
        for quote, amount, payout in zip(ordered_quotes, amounts, payouts, strict=True)
    )
    with localcontext(_MATH_CONTEXT):
        return StakePlan(
            id=stake_plan_id,
            opportunity_id=opportunity.id,
            currency=rounding_policy.currency,
            bankroll=bankroll_value,
            allocations=allocations,
            guaranteed_payout=guaranteed_payout,
            guaranteed_profit=guaranteed_profit,
            created_at=created_at,
        )
