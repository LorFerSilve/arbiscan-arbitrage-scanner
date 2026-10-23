"""Phase 19: real-adapter fixture data through matching, normalization and live state.

The HTTP responses are retained, non-live provider-shaped fixtures. Timestamp,
missing-selection and late-packet variations are explicit synthetic mutations
of the records produced by the two production adapters.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from arbiscan.arbitrage import evaluate_market
from arbiscan.domain import OddsQuote, ProviderId, QuoteStatus, SelectionId
from arbiscan.ingestion import MultiSourceLiveQuoteStore, RealtimeIngestionPolicy
from arbiscan.ingestion.realtime import QuoteStoreDiagnosticCode
from arbiscan.marketbook import build_market_books
from arbiscan.matching import CanonicalRegistry, EventMatchStatus
from arbiscan.normalization import NormalizationIssueCode, normalize_source_snapshot
from arbiscan.providers.oddspapi import ODDSPAPI_PROVIDER_ID
from arbiscan.providers.the_odds_api import THE_ODDS_API_PROVIDER_ID
from tests.integration import test_phase16_5_real_provider_semantics as canonical
from tests.integration import test_phase16_6_real_multisource_coexistence as existing


def _normalize(
    observation: existing._Observation,
    registry: CanonicalRegistry,
    *,
    omit_selection: SelectionId | None = None,
    source_offset: timedelta | None = None,
) -> tuple[tuple[OddsQuote, ...], tuple[NormalizationIssueCode, ...]]:
    hooks, decision = existing._hooks_for_observation(observation, registry)
    assert decision.status is EventMatchStatus.MATCHED
    assert decision.matched_event_id == canonical.EVENT_ID

    markets = []
    for market in observation.snapshot.markets:
        selections = tuple(
            selection
            for selection in market.selections
            if omit_selection is None
            or canonical._selection_id(
                observation.adapter.provider.id, selection.label
            ) != omit_selection
        )
        markets.append(
            replace(
                market,
                selections=selections,
                source_timestamp=(
                    canonical.AS_OF + source_offset
                    if source_offset is not None
                    else market.source_timestamp
                ),
            )
        )
    snapshot = replace(observation.snapshot, markets=tuple(markets))
    normalized = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=hooks,
        event=observation.event,
        snapshot=snapshot,
        registry=registry,
        as_of=canonical.AS_OF,
        freshness_window=canonical.FRESHNESS_WINDOW,
    )
    return normalized.quotes, tuple(issue.code for issue in normalized.issues)


def _book_count(
    registry: CanonicalRegistry,
    store: MultiSourceLiveQuoteStore,
    *,
    at_offset_seconds: int = 0,
) -> int:
    moment = canonical.AS_OF + timedelta(seconds=at_offset_seconds)
    books = build_market_books(
        store.fresh_quotes(as_of=moment),
        registry=registry,
        as_of=moment,
        freshness_window=canonical.FRESHNESS_WINDOW,
        market_ids=(canonical.MARKET_ID,),
    ).books
    for book in books:
        assert book.market.id == canonical.MARKET_ID
        assert {outcome.selection.id for outcome in book.outcomes} == {
            canonical.HOME_SELECTION_ID,
            canonical.DRAW_SELECTION_ID,
            canonical.AWAY_SELECTION_ID,
        }
        assert evaluate_market(book.quotes, book.expected_selection_ids).is_arbitrage
    return len(books)


def _store() -> MultiSourceLiveQuoteStore:
    return MultiSourceLiveQuoteStore(
        RealtimeIngestionPolicy(freshness_window=canonical.FRESHNESS_WINDOW)
    )


def test_fixture_backed_partial_coverage_is_recovered_by_other_real_adapter() -> None:
    registry = canonical._registry()
    api, papi = existing._load_observations()
    assert api.event.external_id != papi.event.external_id

    api_sparse, api_issues = _normalize(
        api, registry, omit_selection=canonical.DRAW_SELECTION_ID
    )
    papi_complete, papi_issues = _normalize(papi, registry)
    assert api_issues == papi_issues == ()
    assert len(api_sparse) == 4
    assert len(papi_complete) == 6
    assert {quote.event_id for quote in (*api_sparse, *papi_complete)} == {
        canonical.EVENT_ID
    }
    assert {quote.market_id for quote in (*api_sparse, *papi_complete)} == {
        canonical.MARKET_ID
    }
    assert not any(quote.selection_id == canonical.DRAW_SELECTION_ID for quote in api_sparse)
    assert any(quote.selection_id == canonical.DRAW_SELECTION_ID for quote in papi_complete)

    store = _store()
    applied = store.apply((*api_sparse, *papi_complete), observed_at=canonical.AS_OF)
    assert applied.rejected_count == 0
    assert _book_count(registry, store) == 1


def test_missing_selection_in_both_adapter_payloads_fails_closed_then_recovers() -> None:
    registry = canonical._registry()
    observations = existing._load_observations()
    sparse: list[OddsQuote] = []
    for observation in observations:
        quotes, issues = _normalize(
            observation, registry, omit_selection=canonical.DRAW_SELECTION_ID
        )
        assert issues == ()
        assert len(quotes) == 4
        sparse.extend(quotes)

    store = _store()
    applied = store.apply(sparse, observed_at=canonical.AS_OF)
    assert applied.rejected_count == 0
    assert len(store.fresh_quotes(as_of=canonical.AS_OF)) > 0
    assert _book_count(registry, store) == 0

    # Only the returning OddsPapi transport restores a required leg; the
    # remaining prices are still inside the source freshness window.
    papi = observations[1]
    full, issues = _normalize(papi, registry)
    assert issues == ()
    returning = tuple(
        replace(
            quote,
            source_timestamp=canonical.AS_OF + timedelta(seconds=20),
            ingested_at=canonical.AS_OF + timedelta(seconds=20),
        )
        for quote in full
        if quote.selection_id == canonical.DRAW_SELECTION_ID
    )
    assert len(returning) == 2
    recovery = store.apply(
        returning, observed_at=canonical.AS_OF + timedelta(seconds=20)
    )
    assert recovery.added_count == 2
    assert recovery.rejected_count == 0
    assert _book_count(registry, store, at_offset_seconds=20) == 1


def test_source_timestamp_skew_fails_closed_before_quotes_reach_market_books() -> None:
    registry = canonical._registry()
    api, papi = existing._load_observations()
    good, issues = _normalize(papi, registry)
    assert issues == ()
    assert len(good) == 6

    for offset, reason in (
        (timedelta(seconds=7), NormalizationIssueCode.FUTURE_SNAPSHOT),
        (
            -canonical.FRESHNESS_WINDOW - timedelta(seconds=1),
            NormalizationIssueCode.STALE_SNAPSHOT,
        ),
    ):
        bad, bad_issues = _normalize(api, registry, source_offset=offset)
        assert bad == ()
        assert bad_issues == (reason, reason)
        store = _store()
        store.apply((*bad, *good), observed_at=canonical.AS_OF)
        assert _book_count(registry, store) == 1
        assert {
            quote.transport_provider_id for quote in store.fresh_quotes(as_of=canonical.AS_OF)
        } == {ODDSPAPI_PROVIDER_ID}


def test_delayed_revision_and_future_clock_skew_do_not_override_new_quote() -> None:
    registry, _observations, quotes = existing._real_quotes()
    api_quote = existing._quote(
        quotes,
        transport_provider_id=THE_ODDS_API_PROVIDER_ID,
        price_provider_id=canonical.PINNACLE_ID,
        selection_id=canonical.DRAW_SELECTION_ID,
    )
    papi_quote = existing._quote(
        quotes,
        transport_provider_id=ODDSPAPI_PROVIDER_ID,
        price_provider_id=canonical.PINNACLE_ID,
        selection_id=canonical.DRAW_SELECTION_ID,
    )
    initial_timestamp = canonical.AS_OF - timedelta(seconds=20)
    first = replace(
        api_quote,
        source_timestamp=initial_timestamp,
        ingested_at=canonical.AS_OF,
        decimal_price=Decimal("3.11"),
    )
    second = replace(
        papi_quote,
        source_timestamp=initial_timestamp,
        ingested_at=canonical.AS_OF,
        decimal_price=Decimal("3.11"),
    )
    store = _store()
    initial = store.apply((first, second), observed_at=canonical.AS_OF)
    assert initial.added_count == 2
    assert store.fresh_quotes(as_of=canonical.AS_OF) == (first,)
    assert store.last_consolidation_result.equivalent_overlap_count == 1

    newer_at = canonical.AS_OF + timedelta(seconds=10)
    newest = replace(
        first,
        source_timestamp=newer_at,
        ingested_at=newer_at,
        decimal_price=Decimal("3.45"),
    )
    assert store.apply((newest,), observed_at=newer_at).updated_count == 1
    assert store.fresh_quotes(as_of=newer_at) == (newest,)

    delayed_at = canonical.AS_OF + timedelta(seconds=11)
    late_old_source = replace(
        first,
        source_timestamp=canonical.AS_OF - timedelta(seconds=40),
        ingested_at=delayed_at,
        decimal_price=Decimal("9.99"),
    )
    future_timestamp = replace(
        first,
        source_timestamp=canonical.AS_OF + timedelta(seconds=30),
        ingested_at=delayed_at,
        decimal_price=Decimal("9.98"),
    )
    rejected = store.apply((late_old_source, future_timestamp), observed_at=delayed_at)
    assert rejected.rejected_count == 2
    assert {diag.code for diag in rejected.diagnostics} == {
        QuoteStoreDiagnosticCode.OUT_OF_ORDER,
        QuoteStoreDiagnosticCode.CLOCK_SKEW_EXCEEDED,
    }
    assert store.fresh_quotes(as_of=delayed_at) == (newest,)
    assert store.last_consolidation_result.conflict_count == 0
    assert all(q.status is QuoteStatus.ACTIVE for q in store.fresh_quotes(as_of=delayed_at))

    # This test targets one shared bookmaker slot, not a complete 1X2
    # market; incomplete market books must remain non-executable.
    assert _book_count(registry, store, at_offset_seconds=11) == 0
