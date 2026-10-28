"""Deterministic demonstration stake plan computed by the actual Python engine.

No provider is connected. Domain quotes are in-memory *synthetic* fixtures;
an ACTIVE internal quote status here is required by the pure math engine
and does not mean that an actionable live bookmaker quote exists.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from arbiscan.api.contracts import (
    OddsResponse,
    OpportunitySummaryResponse,
    StakeLegResponse,
    StakePlanResponse,
)
from arbiscan.arbitrage import (
    CurrencyRoundingPolicy,
    allocate_stakes,
    build_opportunity,
    evaluate_market,
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

_DEMO_BANKROLL = Decimal("100.00")
_EUR = CurrencyRoundingPolicy(currency="EUR", quantum=Decimal("0.01"))


def calculate_demo_projection(
    quotes: tuple[OddsResponse, ...],
    *,
    opportunity_id: str,
    detected_at: str,
) -> tuple[OpportunitySummaryResponse, StakePlanResponse]:
    """Validate a complete synthetic three-way market and round real stakes.

    No client-provided bankroll, market identification or arbitrary odds
    enter this internal-only helper.
    """
    if len(quotes) != 3 or {quote.selection_id for quote in quotes} != {"home", "draw", "away"}:
        raise ValueError("demo must contain exactly three 1X2 outcomes")
    if any(
        quote.status != "synthetic"
        or not quote.quote_id.startswith("synthetic-")
        or not quote.provider_id.startswith("synthetic-")
        or quote.event_id != "synthetic-event-1"
        or quote.market_id != "synthetic-regulation-1x2"
        for quote in quotes
    ):
        raise ValueError("demo source may only use fixed fictional quotes")

    observed = tuple(
        OddsQuote(
            id=QuoteId(quote.quote_id),
            provider_id=ProviderId(quote.provider_id),
            event_id=EventId(quote.event_id),
            market_id=MarketId(quote.market_id),
            selection_id=SelectionId(quote.selection_id),
            decimal_price=Decimal(quote.decimal_price),
            source_event_id=quote.event_id,
            source_market_id=quote.market_id,
            source_selection_id=quote.selection_id,
            ingested_at=datetime.fromisoformat(quote.observed_at),
            status=QuoteStatus.ACTIVE,
            trace_id="synthetic-only-no-external-evidence",
        )
        for quote in quotes
    )
    evaluation = evaluate_market(
        observed, tuple(SelectionId(value) for value in ("home", "draw", "away"))
    )
    if not evaluation.is_arbitrage:
        raise ValueError("demo fixture must be a mathematical theoretical arbitrage")
    opportunity = build_opportunity(
        evaluation,
        opportunity_id=OpportunityId(opportunity_id),
        detected_at=datetime.fromisoformat(detected_at),
    )
    plan = allocate_stakes(
        opportunity,
        observed,
        bankroll=_DEMO_BANKROLL,
        stake_plan_id=StakePlanId("synthetic-plan-1"),
        created_at=datetime.fromisoformat(detected_at),
        rounding_policy=_EUR,
    )
    if plan is None:
        raise ValueError("demo stake plan has no conservatively profitable allocation")
    by_id = {quote.quote_id: quote for quote in quotes}
    result = StakePlanResponse(
        currency=plan.currency,
        bankroll=str(plan.bankroll),
        total_staked=str(sum((allocation.amount for allocation in plan.allocations), Decimal("0"))),
        guaranteed_payout=str(plan.guaranteed_payout),
        guaranteed_profit=str(plan.guaranteed_profit),
        allocations=tuple(
            StakeLegResponse(
                quote_id=allocation.quote_id.value,
                selection_id=allocation.selection_id.value,
                provider_id=allocation.provider_id.value,
                decimal_price=by_id[allocation.quote_id.value].decimal_price,
                stake=str(allocation.amount),
                expected_payout=str(allocation.expected_payout),
            )
            for allocation in plan.allocations
        ),
        assumptions=(
            "Uitsluitend synthetische 1X2-uitkomsten (90 minuten), geen echte weddenschap.",
            "Bankroll EUR 100,00; inzetstappen EUR 0,01; uitbetalingen naar beneden afgerond.",
            "Geen transactiekosten, belastingen, bookmakerlimieten of afwijkende void-regels gemodelleerd.",
            "Winst is uitsluitend gegarandeerd binnen dit wiskundige fictieve model.",
        ),
        synthetic=True,
    )
    summary = OpportunitySummaryResponse(
        opportunity_id=opportunity_id,
        event_id=quotes[0].event_id,
        market_id=quotes[0].market_id,
        implied_probability_sum=str(evaluation.implied_probability_sum),
        guaranteed_profit_rate=str(evaluation.theoretical_profit_margin),
        detected_at=detected_at,
    )
    return summary, result
