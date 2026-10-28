"""Deterministic local-only Phase 20.1 API data: never contacts providers.

`demo=True` deliberately uses imaginary teams/providers and cannot
accidentally present a real, unverified football fixture as actionable.
"""

from __future__ import annotations

from arbiscan.api.demo_stakes import calculate_demo_projection
from arbiscan.api.contracts import (
    EventSummaryResponse,
    OddsResponse,
    OpportunityDetailResponse,
    ProviderStatusResponse,
    SportResponse,
)

_DEMO_EVENT = EventSummaryResponse(
    event_id="synthetic-event-1",
    sport="football",
    competition="Synthetic Test League",
    participant_names=("Example FC", "Sample Town"),
    scheduled_start="2030-06-01T12:00:00+00:00",
    status="synthetic",
)
_DEMO_QUOTES = (
    OddsResponse(
        quote_id="synthetic-quote-home",
        event_id=_DEMO_EVENT.event_id,
        market_id="synthetic-regulation-1x2",
        selection_id="home",
        provider_id="synthetic-source-a",
        decimal_price="2.50",
        status="synthetic",
        observed_at="2030-06-01T11:59:00+00:00",
    ),
    OddsResponse(
        quote_id="synthetic-quote-draw",
        event_id=_DEMO_EVENT.event_id,
        market_id="synthetic-regulation-1x2",
        selection_id="draw",
        provider_id="synthetic-source-b",
        decimal_price="4.00",
        status="synthetic",
        observed_at="2030-06-01T11:59:00+00:00",
    ),
    OddsResponse(
        quote_id="synthetic-quote-away",
        event_id=_DEMO_EVENT.event_id,
        market_id="synthetic-regulation-1x2",
        selection_id="away",
        provider_id="synthetic-source-b",
        decimal_price="4.00",
        status="synthetic",
        observed_at="2030-06-01T11:59:00+00:00",
    ),
)
# The mathematical margin, allocation, payout and profit all come from
# arbiscan.arbitrage, never manually approximated in the browser.
_DEMO_OPPORTUNITY, _DEMO_STAKE_PLAN = calculate_demo_projection(
    _DEMO_QUOTES,
    opportunity_id="synthetic-opportunity-1",
    detected_at="2030-06-01T11:59:30+00:00",
)


class SyntheticApiDataSource:
    """Opt-in fixture source satisfying Phase 13's existing read-only API."""

    def __init__(self, *, demo: bool = False) -> None:
        self.demo = demo

    def readiness_checks(self) -> dict[str, bool]:
        # Real quote ingestion stays blocked, even in demo mode.
        return {"live_provider_ingestion": False, "phase19_quote_authorized": False}

    def provider_statuses(self) -> tuple[ProviderStatusResponse, ...]:
        if not self.demo:
            return ()
        return (
            ProviderStatusResponse("synthetic-source-a", available=False),
            ProviderStatusResponse("synthetic-source-b", available=False),
        )

    def sports(self) -> tuple[SportResponse, ...]:
        return (SportResponse("football"),) if self.demo else ()

    def events(self) -> tuple[EventSummaryResponse, ...]:
        return (_DEMO_EVENT,) if self.demo else ()

    def odds(self) -> tuple[OddsResponse, ...]:
        return _DEMO_QUOTES if self.demo else ()

    def opportunities(self) -> tuple[OpportunitySummaryResponse, ...]:
        return (_DEMO_OPPORTUNITY,) if self.demo else ()

    def opportunity(self, opportunity_id: str) -> OpportunityDetailResponse | None:
        if not self.demo or opportunity_id != _DEMO_OPPORTUNITY.opportunity_id:
            return None
        return OpportunityDetailResponse(
            opportunity=_DEMO_OPPORTUNITY,
            quote_ids=tuple(quote.quote_id for quote in _DEMO_QUOTES),
            evidence_available=False,
            stake_plan=_DEMO_STAKE_PLAN,
        )

    def metrics(self) -> dict[str, int | float]:
        return {
            "active_quotes": 0,
            "actionable_opportunities": 0,
            "synthetic_quotes": len(_DEMO_QUOTES) if self.demo else 0,
            "synthetic_opportunities": 1 if self.demo else 0,
        }
