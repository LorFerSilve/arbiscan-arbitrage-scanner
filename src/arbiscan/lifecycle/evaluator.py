"""Practical, fail-closed opportunity revalidation."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from arbiscan.arbitrage.core import evaluate_market
from arbiscan.arbitrage.staking import allocate_stakes
from arbiscan.domain import OddsQuote, Opportunity, QuoteStatus, StakePlanId
from arbiscan.lifecycle.models import (
    ActionabilityPolicy,
    LifecycleEvaluation,
    LifecycleReason,
    LifecycleState,
    OperationalAssumptions,
)

_CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)
_ZERO = Decimal("0")


def _assumptions(policy: ActionabilityPolicy) -> OperationalAssumptions:
    exposure = min(policy.bankroll, policy.maximum_exposure or policy.bankroll)
    return OperationalAssumptions(
        currency=policy.rounding_policy.currency,
        bankroll=policy.bankroll,
        maximum_exposure=exposure,
        minimum_guaranteed_profit=policy.minimum_guaranteed_profit,
        minimum_roi=policy.minimum_roi,
        maximum_quote_age_seconds=policy.maximum_quote_age_seconds,
        maximum_margin_drift=policy.maximum_margin_drift,
        commission_rate=policy.commission_rate,
        tax_rate=policy.tax_rate,
    )


def _result(
    *,
    state: LifecycleState,
    reason: LifecycleReason,
    margin: Decimal,
    policy: ActionabilityPolicy,
) -> LifecycleEvaluation:
    return LifecycleEvaluation(
        state=state,
        reason=reason,
        theoretical_profit_margin=margin,
        stake_plan=None,
        gross_guaranteed_profit=None,
        net_guaranteed_profit=None,
        net_roi=None,
        assumptions=_assumptions(policy),
    )


def revalidate_opportunity(
    opportunity: Opportunity,
    current_quotes: tuple[OddsQuote, ...],
    *,
    now: datetime,
    stake_plan_id: StakePlanId,
    policy: ActionabilityPolicy,
) -> LifecycleEvaluation:
    """Revalidate current prices and operational constraints before surfacing actionability.

    The function is deliberately fail closed: stale/closed/replaced quotes, lost
    arbitrage, excessive drift, infeasible rounded stakes, or net-profit/ROI
    thresholds all prevent ACTIONABLE output.
    """
    if not isinstance(opportunity, Opportunity):
        raise TypeError("opportunity must be Opportunity")
    if not isinstance(policy, ActionabilityPolicy):
        raise TypeError("policy must be ActionabilityPolicy")
    if not isinstance(stake_plan_id, StakePlanId):
        raise TypeError("stake_plan_id must be StakePlanId")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    quotes = tuple(current_quotes)
    if len(quotes) < 2 or any(not isinstance(quote, OddsQuote) for quote in quotes):
        return _result(
            state=LifecycleState.INVALIDATED,
            reason=LifecycleReason.QUOTE_SET_CHANGED,
            margin=_ZERO,
            policy=policy,
        )
    if {quote.id for quote in quotes} != set(opportunity.quote_ids):
        return _result(
            state=LifecycleState.INVALIDATED,
            reason=LifecycleReason.QUOTE_SET_CHANGED,
            margin=_ZERO,
            policy=policy,
        )
    if any(quote.status is not QuoteStatus.ACTIVE for quote in quotes):
        return _result(
            state=LifecycleState.EXPIRED,
            reason=LifecycleReason.MARKET_CLOSED,
            margin=_ZERO,
            policy=policy,
        )

    for quote in quotes:
        observed_at = quote.source_timestamp or quote.ingested_at
        with localcontext(_CONTEXT):
            age = Decimal(str((now - observed_at).total_seconds()))
        if age < _ZERO or age > policy.maximum_quote_age_seconds:
            return _result(
                state=LifecycleState.STALE,
                reason=LifecycleReason.STALE_QUOTES,
                margin=_ZERO,
                policy=policy,
            )

    expected = tuple(quote.selection_id for quote in quotes)
    evaluation = evaluate_market(quotes, expected)
    if not evaluation.is_arbitrage:
        return _result(
            state=LifecycleState.INVALIDATED,
            reason=LifecycleReason.NO_LONGER_ARBITRAGE,
            margin=evaluation.theoretical_profit_margin,
            policy=policy,
        )

    if policy.maximum_margin_drift is not None:
        with localcontext(_CONTEXT):
            deterioration = (
                opportunity.theoretical_profit_margin - evaluation.theoretical_profit_margin
            )
        if deterioration > policy.maximum_margin_drift:
            return _result(
                state=LifecycleState.INVALIDATED,
                reason=LifecycleReason.ODDS_DRIFT_EXCEEDED,
                margin=evaluation.theoretical_profit_margin,
                policy=policy,
            )

    revalidated = Opportunity(
        id=opportunity.id,
        event_id=opportunity.event_id,
        market_id=opportunity.market_id,
        quote_ids=tuple(quote.id for quote in evaluation.quotes),
        implied_probability_sum=evaluation.implied_probability_sum,
        theoretical_profit_margin=evaluation.theoretical_profit_margin,
        detected_at=opportunity.detected_at,
    )
    exposure = min(policy.bankroll, policy.maximum_exposure or policy.bankroll)
    plan = allocate_stakes(
        revalidated,
        evaluation.quotes,
        bankroll=exposure,
        stake_plan_id=stake_plan_id,
        created_at=now,
        rounding_policy=policy.rounding_policy,
        constraints=policy.stake_constraints,
    )
    if plan is None:
        return _result(
            state=LifecycleState.VALIDATED,
            reason=LifecycleReason.STAKE_CONSTRAINTS,
            margin=evaluation.theoretical_profit_margin,
            policy=policy,
        )

    gross_profit = plan.guaranteed_profit
    with localcontext(_CONTEXT):
        commission = gross_profit * policy.commission_rate
        taxable_after_commission = max(_ZERO, gross_profit - commission)
        tax = taxable_after_commission * policy.tax_rate
        net_profit = gross_profit - commission - tax
        total_staked = sum((allocation.amount for allocation in plan.allocations), _ZERO)
        net_roi = net_profit / total_staked if total_staked > _ZERO else _ZERO

    if net_profit < policy.minimum_guaranteed_profit or net_profit <= _ZERO:
        reason = LifecycleReason.MINIMUM_PROFIT
        state = LifecycleState.VALIDATED
    elif net_roi < policy.minimum_roi:
        reason = LifecycleReason.MINIMUM_ROI
        state = LifecycleState.VALIDATED
    else:
        reason = LifecycleReason.ACTIONABLE
        state = LifecycleState.ACTIONABLE

    return LifecycleEvaluation(
        state=state,
        reason=reason,
        theoretical_profit_margin=evaluation.theoretical_profit_margin,
        stake_plan=plan,
        gross_guaranteed_profit=gross_profit,
        net_guaranteed_profit=net_profit,
        net_roi=net_roi,
        assumptions=_assumptions(policy),
    )
