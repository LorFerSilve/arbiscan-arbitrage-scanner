"""Phase 19 regression for diagnostic-heavy multi-market book construction."""

from dataclasses import replace
from datetime import timedelta

from scripts.benchmark_detection import START, _quote, _workload

from arbiscan.domain import EventId, MarketId, QuoteId, QuoteStatus
from arbiscan.marketbook import MarketBookDiagnosticCode, build_market_books


def test_diagnostic_index_preserves_global_and_per_market_results() -> None:
    registry, specs = _workload(events=3, markets_per_event=2, providers=2)
    valid = tuple(_quote(spec, at=START, revision=0) for spec in specs)
    inactive = tuple(
        replace(_quote(spec, at=START, revision=1), status=QuoteStatus.SUSPENDED)
        for spec in specs
    )
    unknown_event = replace(
        valid[0], id=QuoteId("quote:unknown-event"), event_id=EventId("event:unknown")
    )
    unknown_market = replace(
        valid[0], id=QuoteId("quote:unknown-market"), market_id=MarketId("market:unknown")
    )
    quotes = (*valid, *inactive, unknown_event, unknown_market)

    first = build_market_books(
        quotes,
        registry=registry,
        as_of=START,
        freshness_window=timedelta(minutes=5),
    )
    reversed_input = build_market_books(
        reversed(quotes),
        registry=registry,
        as_of=START,
        freshness_window=timedelta(minutes=5),
    )

    assert first == reversed_input
    assert len(first.books) == 6
    assert len(first.diagnostics) == len(inactive) + 2
    assert {item.code for item in first.diagnostics} == {
        MarketBookDiagnosticCode.INACTIVE_QUOTE,
        MarketBookDiagnosticCode.UNKNOWN_EVENT,
        MarketBookDiagnosticCode.UNKNOWN_MARKET,
    }
    for book in first.books:
        assert book.construction_diagnostics == tuple(
            item for item in first.diagnostics if item.market_id == book.market.id
        )
        assert any(
            item.code is MarketBookDiagnosticCode.INACTIVE_QUOTE
            for item in book.construction_diagnostics
        )
    assert all(
        item.market_id != MarketId("market:unknown")
        for book in first.books
        for item in book.construction_diagnostics
    )


def test_diagnostic_index_honors_market_scope() -> None:
    registry, specs = _workload(events=2, markets_per_event=2, providers=2)
    quotes = tuple(
        replace(_quote(spec, at=START, revision=1), status=QuoteStatus.SUSPENDED)
        for spec in specs
    )
    selected = registry.markets[0].id
    batch = build_market_books(
        quotes,
        registry=registry,
        as_of=START,
        freshness_window=timedelta(minutes=5),
        market_ids=(selected,),
    )

    assert not batch.books
    assert all(item.market_id == selected for item in batch.diagnostics)
    assert any(
        item.code is MarketBookDiagnosticCode.INCOMPLETE_MARKET for item in batch.diagnostics
    )
