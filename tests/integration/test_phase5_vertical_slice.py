"""End-to-end tests for the deterministic Phase 5 provider pipeline."""

import asyncio
from decimal import Decimal

from arbiscan.domain import EventId, ProviderId, Sport
from arbiscan.normalization import NormalizationIssueCode
from arbiscan.providers import ProviderErrorKind, build_phase5_synthetic_scenario
from arbiscan.services import BookIssueCode, VerticalSliceResult, run_vertical_slice


def _run(*, minimum_profit_margin: Decimal = Decimal("0")) -> VerticalSliceResult:
    scenario = build_phase5_synthetic_scenario()
    return asyncio.run(
        run_vertical_slice(
            adapters=scenario.adapters,
            registry=scenario.registry,
            sport=Sport.FOOTBALL,
            as_of=scenario.as_of,
            freshness_window=scenario.freshness_window,
            minimum_profit_margin=minimum_profit_margin,
            provider_policy=scenario.provider_policy,
        )
    )


def test_vertical_slice_detects_only_the_cross_provider_arbitrage() -> None:
    result = _run()

    assert len(result.opportunities) == 1
    opportunity = result.opportunities[0]
    assert opportunity.event_id == EventId("event:phase5:arb")

    evaluation = next(
        value for value in result.evaluations if value.event_id == opportunity.event_id
    )
    selected_providers = {
        quote.selection_id.value: quote.provider_id for quote in evaluation.quotes
    }
    assert selected_providers["selection:phase5:arb:home"] == ProviderId(
        "provider:synthetic-beta"
    )
    assert selected_providers["selection:phase5:arb:draw"] == ProviderId(
        "provider:synthetic-alpha"
    )
    assert selected_providers["selection:phase5:arb:away"] == ProviderId(
        "provider:synthetic-beta"
    )


def test_no_arbitrage_market_is_evaluated_without_emitting_opportunity() -> None:
    result = _run()

    evaluation = next(
        value
        for value in result.evaluations
        if value.event_id == EventId("event:phase5:noarb")
    )
    assert not evaluation.is_arbitrage
    assert evaluation.implied_probability_sum > Decimal("1")


def test_failure_matrix_fails_closed_without_blocking_healthy_data() -> None:
    result = _run()

    assert len(result.ingestion.snapshots) == 8
    assert len(result.ingestion.issues) == 1
    outage = result.ingestion.issues[0]
    assert outage.provider_id == ProviderId("provider:synthetic-gamma")
    assert outage.kind is ProviderErrorKind.TIMEOUT

    codes = {issue.code for issue in result.normalization_issues}
    assert NormalizationIssueCode.STALE_SNAPSHOT in codes
    assert NormalizationIssueCode.INACTIVE_MARKET in codes
    assert NormalizationIssueCode.MALFORMED_PRICE in codes
    assert NormalizationIssueCode.UNMAPPED_EVENT in codes

    assert not any(quote.source_event_id == "beta:lookalike" for quote in result.quotes)
    assert len(result.quotes) == 14
    assert len(result.evaluations) == 2
    assert {issue.code for issue in result.book_issues} == {
        BookIssueCode.INCOMPLETE_MARKET
    }
    assert len(result.book_issues) == 3


def test_synthetic_pipeline_is_deterministic_across_repeated_runs() -> None:
    first = _run()
    second = _run()

    assert first.quotes == second.quotes
    assert first.normalization_issues == second.normalization_issues
    assert first.evaluations == second.evaluations
    assert first.opportunities == second.opportunities
    assert first.book_issues == second.book_issues


def test_minimum_profit_threshold_can_suppress_theoretical_opportunity() -> None:
    result = _run(minimum_profit_margin=Decimal("0.25"))

    assert result.opportunities == ()
    arb_evaluation = next(
        value
        for value in result.evaluations
        if value.event_id == EventId("event:phase5:arb")
    )
    assert not arb_evaluation.is_arbitrage
