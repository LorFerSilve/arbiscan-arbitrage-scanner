"""Integration regressions for Phase-9 market books in the vertical slice."""

import asyncio

from arbiscan.domain import EventId, ProviderId, Sport
from arbiscan.marketbook import MarketBookDiagnosticCode, ProviderBookPolicy
from arbiscan.providers.synthetic import build_phase5_synthetic_scenario
from arbiscan.services import run_vertical_slice


def _run(*, policy: ProviderBookPolicy | None = None):
    scenario = build_phase5_synthetic_scenario()
    return asyncio.run(
        run_vertical_slice(
            adapters=scenario.adapters,
            registry=scenario.registry,
            sport=Sport.FOOTBALL,
            as_of=scenario.as_of,
            freshness_window=scenario.freshness_window,
            provider_policy=scenario.provider_policy,
            book_provider_policy=policy,
        )
    )


def test_arbitrage_evaluation_consumes_exact_phase9_best_price_book() -> None:
    result = _run()

    assert len(result.market_books) == 2
    arb_book = next(
        book for book in result.market_books if book.event.id == EventId("event:phase5:arb")
    )
    evaluation = next(value for value in result.evaluations if value.event_id == arb_book.event.id)

    assert evaluation.quotes == arb_book.quotes
    assert evaluation.expected_selection_ids == arb_book.expected_selection_ids
    assert result.opportunities[0].quote_ids == tuple(quote.id for quote in arb_book.quotes)


def test_phase9_reports_incomplete_markets_before_arbitrage_math() -> None:
    result = _run()

    incomplete = tuple(
        diagnostic
        for diagnostic in result.market_book_diagnostics
        if diagnostic.code is MarketBookDiagnosticCode.INCOMPLETE_MARKET
    )
    assert len(incomplete) == 3
    assert len(result.evaluations) == len(result.market_books) == 2


def test_provider_filter_is_applied_before_best_price_selection() -> None:
    result = _run(
        policy=ProviderBookPolicy(
            excluded_provider_ids=(ProviderId("provider:synthetic-beta"),),
        )
    )

    assert result.market_books
    assert all(
        outcome.provider_id != ProviderId("provider:synthetic-beta")
        for book in result.market_books
        for outcome in book.outcomes
    )
    assert MarketBookDiagnosticCode.PROVIDER_FILTERED in {
        diagnostic.code for diagnostic in result.market_book_diagnostics
    }
