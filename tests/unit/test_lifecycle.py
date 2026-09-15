"""Phase 12 opportunity lifecycle and execution-realism tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.arbitrage import CurrencyRoundingPolicy, build_opportunity, evaluate_market
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
from arbiscan.lifecycle import (
    ActionabilityPolicy,
    LifecycleReason,
    LifecycleState,
    revalidate_opportunity,
)

NOW = datetime(2026, 9, 15, 18, 0, tzinfo=UTC)
EUR = CurrencyRoundingPolicy(currency="EUR", quantum=Decimal("0.01"))


def quote(
    selection: str,
    odds: str,
    index: int,
    *,
    age: int = 0,
    status: QuoteStatus = QuoteStatus.ACTIVE,
) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:{index}"),
        provider_id=ProviderId(f"provider:{index}"),
        event_id=EventId("event:phase12"),
        market_id=MarketId("market:phase12"),
        selection_id=SelectionId(selection),
        decimal_price=Decimal(odds),
        source_event_id="source:event",
        source_market_id="source:market",
        source_selection_id=selection,
        ingested_at=NOW - timedelta(seconds=age),
        status=status,
        trace_id=f"trace:{index}",
    )


def opportunity(quotes: tuple[OddsQuote, ...]) -> Opportunity:
    evaluation = evaluate_market(quotes, tuple(item.selection_id for item in quotes))
    return build_opportunity(
        evaluation,
        opportunity_id=OpportunityId("opportunity:phase12"),
        detected_at=NOW,
    )


def policy(
    *,
    maximum_exposure: Decimal | None = None,
    minimum_guaranteed_profit: Decimal = Decimal("0"),
    minimum_roi: Decimal = Decimal("0"),
    commission_rate: Decimal = Decimal("0"),
    tax_rate: Decimal = Decimal("0"),
) -> ActionabilityPolicy:
    return ActionabilityPolicy(
        bankroll=Decimal("100"),
        rounding_policy=EUR,
        maximum_quote_age_seconds=Decimal("30"),
        maximum_exposure=maximum_exposure,
        minimum_guaranteed_profit=minimum_guaranteed_profit,
        minimum_roi=minimum_roi,
        commission_rate=commission_rate,
        tax_rate=tax_rate,
    )


def test_fresh_profitable_opportunity_becomes_actionable() -> None:
    quotes = (quote("a", "2.20", 1), quote("b", "2.20", 2))
    result = revalidate_opportunity(
        opportunity(quotes),
        quotes,
        now=NOW,
        stake_plan_id=StakePlanId("plan:1"),
        policy=policy(),
    )
    assert result.state is LifecycleState.ACTIONABLE
    assert result.reason is LifecycleReason.ACTIONABLE
    assert result.stake_plan is not None
    assert result.net_guaranteed_profit == Decimal("10.00")
    assert result.net_roi == Decimal("0.10")


def test_stale_quote_fails_closed_before_staking() -> None:
    detected = (quote("a", "2.20", 1), quote("b", "2.20", 2))
    current = (quote("a", "2.20", 1, age=31), quote("b", "2.20", 2))
    result = revalidate_opportunity(
        opportunity(detected),
        current,
        now=NOW,
        stake_plan_id=StakePlanId("plan:stale"),
        policy=policy(),
    )
    assert result.state is LifecycleState.STALE
    assert result.reason is LifecycleReason.STALE_QUOTES
    assert result.stake_plan is None


def test_closed_market_expires_opportunity() -> None:
    detected = (quote("a", "2.20", 1), quote("b", "2.20", 2))
    current = (
        quote("a", "2.20", 1, status=QuoteStatus.SUSPENDED),
        quote("b", "2.20", 2),
    )
    result = revalidate_opportunity(
        opportunity(detected),
        current,
        now=NOW,
        stake_plan_id=StakePlanId("plan:closed"),
        policy=policy(),
    )
    assert result.state is LifecycleState.EXPIRED
    assert result.reason is LifecycleReason.MARKET_CLOSED


def test_price_drift_that_removes_arbitrage_invalidates() -> None:
    detected = (quote("a", "2.20", 1), quote("b", "2.20", 2))
    current = (quote("a", "1.90", 1), quote("b", "1.90", 2))
    result = revalidate_opportunity(
        opportunity(detected),
        current,
        now=NOW,
        stake_plan_id=StakePlanId("plan:drift"),
        policy=policy(),
    )
    assert result.state is LifecycleState.INVALIDATED
    assert result.reason is LifecycleReason.NO_LONGER_ARBITRAGE


def test_post_rounding_net_profit_threshold_is_enforced() -> None:
    quotes = (quote("a", "2.20", 1), quote("b", "2.20", 2))
    result = revalidate_opportunity(
        opportunity(quotes),
        quotes,
        now=NOW,
        stake_plan_id=StakePlanId("plan:fees"),
        policy=policy(
            commission_rate=Decimal("0.20"),
            tax_rate=Decimal("0.25"),
            minimum_guaranteed_profit=Decimal("7"),
        ),
    )
    assert result.state is LifecycleState.VALIDATED
    assert result.reason is LifecycleReason.MINIMUM_PROFIT
    assert result.gross_guaranteed_profit == Decimal("10.00")
    assert result.net_guaranteed_profit == Decimal("6.0000")


def test_maximum_exposure_and_minimum_roi_are_applied() -> None:
    quotes = (quote("a", "2.20", 1), quote("b", "2.20", 2))
    result = revalidate_opportunity(
        opportunity(quotes),
        quotes,
        now=NOW,
        stake_plan_id=StakePlanId("plan:exposure"),
        policy=policy(maximum_exposure=Decimal("40"), minimum_roi=Decimal("0.11")),
    )
    assert result.stake_plan is not None
    assert result.stake_plan.bankroll == Decimal("40")
    assert result.state is LifecycleState.VALIDATED
    assert result.reason is LifecycleReason.MINIMUM_ROI
