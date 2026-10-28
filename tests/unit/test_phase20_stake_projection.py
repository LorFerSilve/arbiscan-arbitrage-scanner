"""Phase 20.3: engine-calculated synthetic stakes and fail-closed input."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from arbiscan.api.contracts import OpportunityDetailResponse
from arbiscan.api.demo_stakes import calculate_demo_projection
from arbiscan.api.synthetic import SyntheticApiDataSource


def _fixture() -> tuple[SyntheticApiDataSource, OpportunityDetailResponse]:
    source = SyntheticApiDataSource(demo=True)
    detail = source.opportunity("synthetic-opportunity-1")
    assert detail is not None
    return source, detail


def test_real_arbitrage_engine_owns_the_synthetic_margin_and_rounded_stakes() -> None:
    source, detail = _fixture()
    plan = detail.stake_plan
    assert plan is not None
    assert plan.synthetic
    assert plan.currency == "EUR"
    assert plan.bankroll == "100.00"
    assert len(plan.allocations) == 3
    assert {item.selection_id for item in plan.allocations} == {"home", "draw", "away"}
    assert Decimal(detail.opportunity.implied_probability_sum) == Decimal("0.90")
    assert Decimal(detail.opportunity.guaranteed_profit_rate) > Decimal("0.11")
    assert Decimal(detail.opportunity.guaranteed_profit_rate) < Decimal("0.12")
    amounts = [Decimal(item.stake) for item in plan.allocations]
    payouts = [Decimal(item.expected_payout) for item in plan.allocations]
    total = sum(amounts, Decimal("0"))
    assert total == Decimal(plan.total_staked)
    assert total <= Decimal(plan.bankroll)
    assert min(payouts) == Decimal(plan.guaranteed_payout)
    assert min(payouts) - total == Decimal(plan.guaranteed_profit)
    assert Decimal(plan.guaranteed_profit) > 0
    for value in (*amounts, *payouts):
        assert value % Decimal("0.01") == 0
    assert detail.evidence_available is False
    assert source.readiness_checks()["phase19_quote_authorized"] is False
    assert source.metrics()["actionable_opportunities"] == 0
    assert "Geen transactiekosten" in " ".join(plan.assumptions)


def test_summary_ratios_derived_from_engine_not_manual_browser_guess() -> None:
    source, detail = _fixture()
    summary, plan = calculate_demo_projection(
        source.odds(),
        opportunity_id=detail.opportunity.opportunity_id,
        detected_at=detail.opportunity.detected_at,
    )
    assert summary == detail.opportunity
    assert plan == detail.stake_plan
    assert {leg.quote_id for leg in plan.allocations} == set(detail.quote_ids)


def test_invalid_synthetic_quotes_are_rejected_before_core_math_or_display() -> None:
    source, detail = _fixture()
    quotes = source.odds()
    altered = (
        quotes[:2],
        (replace(quotes[0], provider_id="real-bookmaker"), *quotes[1:]),
        (replace(quotes[0], status="active"), *quotes[1:]),
        (replace(quotes[0], event_id="real-event"), *quotes[1:]),
        (replace(quotes[0], selection_id="draw"), *quotes[1:]),
    )
    for fixture in altered:
        try:
            calculate_demo_projection(
                tuple(fixture),
                opportunity_id=detail.opportunity.opportunity_id,
                detected_at=detail.opportunity.detected_at,
            )
        except ValueError:
            continue
        raise AssertionError("invalid synthetic fixture unexpectedly accepted")


def test_default_empty_mode_never_supplies_a_stake_plan() -> None:
    source = SyntheticApiDataSource()
    assert source.opportunities() == ()
    assert source.odds() == ()
    assert source.opportunity("synthetic-opportunity-1") is None
    assert source.metrics()["synthetic_opportunities"] == 0
