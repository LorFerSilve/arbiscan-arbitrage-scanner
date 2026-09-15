"""Deterministic fail-closed canonical market-book construction."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta

from arbiscan.domain import MarketId, OddsQuote, QuoteStatus, SelectionId
from arbiscan.domain.validation import normalize_datetime
from arbiscan.matching.catalog import CanonicalRegistry
from arbiscan.marketbook.models import (
    BestPriceOutcome,
    CanonicalMarketBook,
    MarketBookBatch,
    MarketBookDiagnostic,
    MarketBookDiagnosticCode,
    MarketBookFreshness,
    ProviderBookPolicy,
)


def quote_effective_timestamp(quote: OddsQuote) -> datetime:
    """Return the timestamp used for freshness decisions for a canonical quote."""
    if not isinstance(quote, OddsQuote):
        raise ValueError("quote must be OddsQuote")
    return quote.source_timestamp or quote.ingested_at


def _diagnostic(
    code: MarketBookDiagnosticCode,
    quote: OddsQuote,
    detail: str,
) -> MarketBookDiagnostic:
    return MarketBookDiagnostic(
        code=code,
        detail=detail,
        event_id=quote.event_id,
        market_id=quote.market_id,
        selection_id=quote.selection_id,
        provider_id=quote.provider_id,
        quote_id=quote.id,
    )


def _best_quote(candidates: tuple[OddsQuote, ...]) -> OddsQuote:
    """Select the highest price, then freshest quote, then stable lexical identity."""
    if not candidates:
        raise ValueError("best-quote selection requires at least one candidate")

    best_price = max(quote.decimal_price for quote in candidates)
    price_ties = tuple(quote for quote in candidates if quote.decimal_price == best_price)
    freshest = max(quote_effective_timestamp(quote) for quote in price_ties)
    freshest_ties = tuple(
        quote for quote in price_ties if quote_effective_timestamp(quote) == freshest
    )
    return min(
        freshest_ties,
        key=lambda quote: (quote.provider_id.value, quote.id.value),
    )


def _diagnostic_sort_key(item: MarketBookDiagnostic) -> tuple[str, ...]:
    return (
        "" if item.event_id is None else item.event_id.value,
        "" if item.market_id is None else item.market_id.value,
        item.code.value,
        "" if item.selection_id is None else item.selection_id.value,
        "" if item.provider_id is None else item.provider_id.value,
        "" if item.quote_id is None else item.quote_id.value,
        item.detail,
    )


def build_market_books(
    quotes: Iterable[OddsQuote],
    *,
    registry: CanonicalRegistry,
    as_of: datetime,
    freshness_window: timedelta,
    provider_policy: ProviderBookPolicy | None = None,
    market_ids: Iterable[MarketId] | None = None,
) -> MarketBookBatch:
    """Construct complete best-price books for canonical markets.

    Quotes must survive canonical identity checks, provider policy, active-status
    checks and freshness checks before they can compete for best price. A market
    is emitted only when every expected canonical selection has one eligible quote.
    """
    if not isinstance(registry, CanonicalRegistry):
        raise ValueError("registry must be CanonicalRegistry")
    now = normalize_datetime(as_of, field="market_book.as_of")
    if not isinstance(freshness_window, timedelta) or freshness_window <= timedelta(0):
        raise ValueError("freshness_window must be a positive timedelta")
    policy = ProviderBookPolicy() if provider_policy is None else provider_policy
    if not isinstance(policy, ProviderBookPolicy):
        raise ValueError("provider_policy must be ProviderBookPolicy")

    quote_values = tuple(quotes)
    if any(not isinstance(quote, OddsQuote) for quote in quote_values):
        raise ValueError("quotes must contain OddsQuote values")

    if market_ids is None:
        scoped_market_ids = tuple(
            sorted((market.id for market in registry.markets), key=lambda value: value.value)
        )
    else:
        scoped_market_ids = tuple(market_ids)
        if any(not isinstance(market_id, MarketId) for market_id in scoped_market_ids):
            raise ValueError("market_ids must contain MarketId values")
        if len(set(scoped_market_ids)) != len(scoped_market_ids):
            raise ValueError("market_ids must be unique")
        unknown_scope = [
            market_id.value
            for market_id in scoped_market_ids
            if registry.market(market_id) is None
        ]
        if unknown_scope:
            raise ValueError(f"market_ids contain unknown canonical markets: {sorted(unknown_scope)}")
        scoped_market_ids = tuple(sorted(scoped_market_ids, key=lambda value: value.value))

    scope_set = set(scoped_market_ids)
    diagnostics: list[MarketBookDiagnostic] = []
    eligible_by_market_selection: dict[
        MarketId,
        dict[SelectionId, list[OddsQuote]],
    ] = defaultdict(lambda: defaultdict(list))

    id_counts = Counter(quote.id for quote in quote_values)
    duplicate_ids = {quote_id for quote_id, count in id_counts.items() if count > 1}
    duplicate_reported: set[object] = set()

    for quote in quote_values:
        if quote.id in duplicate_ids:
            if quote.id not in duplicate_reported:
                diagnostics.append(
                    _diagnostic(
                        MarketBookDiagnosticCode.DUPLICATE_QUOTE_ID,
                        quote,
                        "duplicate quote ID makes quote provenance ambiguous",
                    )
                )
                duplicate_reported.add(quote.id)
            continue

        canonical_event = registry.event(quote.event_id)
        if canonical_event is None:
            diagnostics.append(
                _diagnostic(
                    MarketBookDiagnosticCode.UNKNOWN_EVENT,
                    quote,
                    "quote references an unknown canonical event",
                )
            )
            continue

        canonical_market = registry.market(quote.market_id)
        if canonical_market is None:
            diagnostics.append(
                _diagnostic(
                    MarketBookDiagnosticCode.UNKNOWN_MARKET,
                    quote,
                    "quote references an unknown canonical market",
                )
            )
            continue

        canonical_selection = registry.selection(quote.selection_id)
        if canonical_selection is None:
            diagnostics.append(
                _diagnostic(
                    MarketBookDiagnosticCode.UNKNOWN_SELECTION,
                    quote,
                    "quote references an unknown canonical selection",
                )
            )
            continue

        if canonical_market.event_id != quote.event_id:
            diagnostics.append(
                _diagnostic(
                    MarketBookDiagnosticCode.QUOTE_EVENT_MISMATCH,
                    quote,
                    "quote event does not match the canonical market event",
                )
            )
            continue
        if canonical_selection.market_id != quote.market_id:
            diagnostics.append(
                _diagnostic(
                    MarketBookDiagnosticCode.QUOTE_SELECTION_MISMATCH,
                    quote,
                    "quote selection does not belong to the canonical market",
                )
            )
            continue

        if quote.market_id not in scope_set:
            continue
        if not policy.allows(quote.provider_id):
            diagnostics.append(
                _diagnostic(
                    MarketBookDiagnosticCode.PROVIDER_FILTERED,
                    quote,
                    "quote provider is excluded by the market-book policy",
                )
            )
            continue
        if quote.status is not QuoteStatus.ACTIVE:
            diagnostics.append(
                _diagnostic(
                    MarketBookDiagnosticCode.INACTIVE_QUOTE,
                    quote,
                    f"quote status {quote.status.value!r} is not active",
                )
            )
            continue

        effective_at = quote_effective_timestamp(quote)
        age = now - effective_at
        if age < timedelta(0):
            diagnostics.append(
                _diagnostic(
                    MarketBookDiagnosticCode.FUTURE_QUOTE,
                    quote,
                    "quote effective timestamp lies after market-book construction time",
                )
            )
            continue
        if age > freshness_window:
            diagnostics.append(
                _diagnostic(
                    MarketBookDiagnosticCode.STALE_QUOTE,
                    quote,
                    f"quote age {age} exceeds freshness window {freshness_window}",
                )
            )
            continue

        eligible_by_market_selection[quote.market_id][quote.selection_id].append(quote)

    books: list[CanonicalMarketBook] = []
    for market_id in scoped_market_ids:
        market = registry.market(market_id)
        if market is None:
            raise AssertionError("validated market scope must resolve in registry")
        event = registry.event(market.event_id)
        if event is None:
            raise AssertionError("validated canonical market must resolve its event")

        expected = registry.selection_ids_for_market(market.id)
        if len(expected) < 2:
            diagnostics.append(
                MarketBookDiagnostic(
                    code=MarketBookDiagnosticCode.INSUFFICIENT_OUTCOMES,
                    event_id=event.id,
                    market_id=market.id,
                    detail="canonical market defines fewer than two outcomes",
                )
            )
            continue

        candidate_map = eligible_by_market_selection.get(market.id, {})
        missing = tuple(
            selection_id for selection_id in expected if not candidate_map.get(selection_id)
        )
        if missing:
            diagnostics.append(
                MarketBookDiagnostic(
                    code=MarketBookDiagnosticCode.INCOMPLETE_MARKET,
                    event_id=event.id,
                    market_id=market.id,
                    detail=(
                        "missing eligible canonical selections: "
                        f"{[selection_id.value for selection_id in missing]}"
                    ),
                )
            )
            continue

        outcomes: list[BestPriceOutcome] = []
        for selection_id in expected:
            selection = registry.selection(selection_id)
            if selection is None:
                raise AssertionError("registry selection IDs must resolve")
            candidates = tuple(candidate_map[selection_id])
            outcomes.append(
                BestPriceOutcome(
                    selection=selection,
                    quote=_best_quote(candidates),
                )
            )

        selected_timestamps = tuple(
            quote_effective_timestamp(outcome.quote) for outcome in outcomes
        )
        market_diagnostics = tuple(
            sorted(
                (item for item in diagnostics if item.market_id == market.id),
                key=_diagnostic_sort_key,
            )
        )
        books.append(
            CanonicalMarketBook(
                event=event,
                market=market,
                expected_selection_ids=expected,
                outcomes=tuple(outcomes),
                freshness=MarketBookFreshness(
                    as_of=now,
                    freshness_window=freshness_window,
                    oldest_quote_at=min(selected_timestamps),
                    newest_quote_at=max(selected_timestamps),
                ),
                construction_diagnostics=market_diagnostics,
            )
        )

    return MarketBookBatch(
        books=tuple(sorted(books, key=lambda book: (book.event.id.value, book.market.id.value))),
        diagnostics=tuple(sorted(diagnostics, key=_diagnostic_sort_key)),
    )
