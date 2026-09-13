"""Stake-allocation tests for limits, increments, currency rounding, and safety."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.arbitrage import (
    CurrencyRoundingPolicy,
    StakeConstraint,
    StakeConstraintError,
    allocate_stakes,
    build_opportunity,
    evaluate_market,
)
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
    StakePlanId,
)

NOW = datetime(2026, 9, 13, 13, 0, tzinfo=UTC)
EUR = CurrencyRoundingPolicy(currency="EUR", quantum=Decimal("0.01"))


def expect_stake_constraint_error(action: Callable[[], object], *, contains: str) -> None:
    try:
        action()
    except StakeConstraintError as exc:
        if contains not in str(exc):
            raise AssertionError(f"expected error containing {contains!r}, got {exc!r}") from exc
        return
    raise AssertionError("expected StakeConstraintError")


def make_quote(selection: str, odds: str, *, index: int) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:{index}"),
        provider_id=ProviderId(f"provider:{index}"),
        event_id=EventId("event:stake"),
        market_id=MarketId("market:stake"),
        selection_id=SelectionId(selection),
        decimal_price=Decimal(odds),
        source_event_id="source:event",
        source_market_id="source:market",
        source_selection_id=selection,
        ingested_at=NOW,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{index}",
    )


def make_opportunity(quotes: tuple[OddsQuote, ...]) -> Opportunity:
    evaluation = evaluate_market(quotes, tuple(quote.selection_id for quote in quotes))
    return build_opportunity(
        evaluation,
        opportunity_id=OpportunityId("opportunity:stake"),
        detected_at=NOW,
    )


def test_unconstrained_two_way_allocation_equalizes_payout() -> None:
    quotes = (
        make_quote("selection:a", "2.20", index=1),
        make_quote("selection:b", "2.20", index=2),
    )
    opportunity = make_opportunity(quotes)

    plan = allocate_stakes(
        opportunity,
        quotes,
        bankroll=Decimal("100"),
        stake_plan_id=StakePlanId("stake-plan:1"),
        created_at=NOW,
        rounding_policy=EUR,
    )

    assert plan is not None
    assert tuple(allocation.amount for allocation in plan.allocations) == (
        Decimal("50.00"),
        Decimal("50.00"),
    )
    assert plan.guaranteed_payout == Decimal("110.00")
    assert plan.guaranteed_profit == Decimal("10.00")


def test_three_way_rounding_remains_profitable_and_nearly_equalized() -> None:
    quotes = tuple(
        make_quote(f"selection:{index}", "3.60", index=index) for index in range(1, 4)
    )
    opportunity = make_opportunity(quotes)

    plan = allocate_stakes(
        opportunity,
        quotes,
        bankroll=Decimal("100"),
        stake_plan_id=StakePlanId("stake-plan:3-way"),
        created_at=NOW,
        rounding_policy=EUR,
    )

    assert plan is not None
    payouts = [allocation.expected_payout for allocation in plan.allocations]
    assert plan.guaranteed_profit > Decimal("0")
    assert max(payouts) - min(payouts) <= Decimal("0.05")
    assert sum((allocation.amount for allocation in plan.allocations), Decimal("0")) <= Decimal(
        "100"
    )


def test_maximum_stake_caps_the_effective_bankroll_without_destroying_profit() -> None:
    quotes = (
        make_quote("selection:a", "2.20", index=1),
        make_quote("selection:b", "2.20", index=2),
    )
    opportunity = make_opportunity(quotes)
    constraints = (
        StakeConstraint(
            quote_id=quotes[0].id,
            maximum_stake=Decimal("10"),
            stake_increment=Decimal("0.01"),
        ),
    )

    plan = allocate_stakes(
        opportunity,
        quotes,
        bankroll=Decimal("100"),
        stake_plan_id=StakePlanId("stake-plan:max"),
        created_at=NOW,
        rounding_policy=EUR,
        constraints=constraints,
    )

    assert plan is not None
    assert max(allocation.amount for allocation in plan.allocations) == Decimal("10.00")
    assert plan.guaranteed_profit == Decimal("2.00")


def test_minimum_stakes_can_make_bankroll_infeasible() -> None:
    quotes = (
        make_quote("selection:a", "2.20", index=1),
        make_quote("selection:b", "2.20", index=2),
    )
    opportunity = make_opportunity(quotes)
    constraints = tuple(
        StakeConstraint(
            quote_id=quote.id,
            minimum_stake=Decimal("10"),
            stake_increment=Decimal("0.01"),
        )
        for quote in quotes
    )

    assert (
        allocate_stakes(
            opportunity,
            quotes,
            bankroll=Decimal("15"),
            stake_plan_id=StakePlanId("stake-plan:too-small"),
            created_at=NOW,
            rounding_policy=EUR,
            constraints=constraints,
        )
        is None
    )


def test_stake_increment_is_respected() -> None:
    quotes = (
        make_quote("selection:a", "2.20", index=1),
        make_quote("selection:b", "2.20", index=2),
    )
    opportunity = make_opportunity(quotes)
    constraints = tuple(
        StakeConstraint(quote_id=quote.id, stake_increment=Decimal("0.05")) for quote in quotes
    )

    plan = allocate_stakes(
        opportunity,
        quotes,
        bankroll=Decimal("99.99"),
        stake_plan_id=StakePlanId("stake-plan:increment"),
        created_at=NOW,
        rounding_policy=EUR,
        constraints=constraints,
    )

    assert plan is not None
    assert all(allocation.amount % Decimal("0.05") == 0 for allocation in plan.allocations)


def test_post_rounding_loss_of_arbitrage_returns_no_guaranteed_plan() -> None:
    quotes = (
        make_quote("selection:a", "2.01", index=1),
        make_quote("selection:b", "2.01", index=2),
    )
    opportunity = make_opportunity(quotes)

    plan = allocate_stakes(
        opportunity,
        quotes,
        bankroll=Decimal("1.00"),
        stake_plan_id=StakePlanId("stake-plan:rounded-away"),
        created_at=NOW,
        rounding_policy=EUR,
    )

    assert plan is None


def test_guaranteed_profit_threshold_is_applied_after_rounding() -> None:
    quotes = (
        make_quote("selection:a", "2.20", index=1),
        make_quote("selection:b", "2.20", index=2),
    )
    opportunity = make_opportunity(quotes)

    plan = allocate_stakes(
        opportunity,
        quotes,
        bankroll=Decimal("100"),
        stake_plan_id=StakePlanId("stake-plan:threshold"),
        created_at=NOW,
        rounding_policy=EUR,
        minimum_guaranteed_profit=Decimal("11"),
    )

    assert plan is None


def test_payouts_are_conservatively_rounded_to_currency_quantum() -> None:
    quotes = (
        make_quote("selection:a", "2.333", index=1),
        make_quote("selection:b", "2.333", index=2),
    )
    opportunity = make_opportunity(quotes)

    plan = allocate_stakes(
        opportunity,
        quotes,
        bankroll=Decimal("10"),
        stake_plan_id=StakePlanId("stake-plan:currency"),
        created_at=NOW,
        rounding_policy=EUR,
    )

    assert plan is not None
    for allocation in plan.allocations:
        assert allocation.expected_payout % EUR.quantum == Decimal("0")
        assert allocation.expected_payout <= allocation.amount * Decimal("2.333")


def test_increment_smaller_than_currency_quantum_is_rejected() -> None:
    quotes = (
        make_quote("selection:a", "2.20", index=1),
        make_quote("selection:b", "2.20", index=2),
    )
    opportunity = make_opportunity(quotes)

    expect_stake_constraint_error(
        lambda: allocate_stakes(
            opportunity,
            quotes,
            bankroll=Decimal("100"),
            stake_plan_id=StakePlanId("stake-plan:bad-grid"),
            created_at=NOW,
            rounding_policy=EUR,
            constraints=(
                StakeConstraint(
                    quote_id=quotes[0].id,
                    stake_increment=Decimal("0.005"),
                ),
            ),
        ),
        contains="currency quantum",
    )
