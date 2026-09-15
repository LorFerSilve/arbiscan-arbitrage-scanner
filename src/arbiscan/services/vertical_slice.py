"""Provider-to-opportunity vertical-slice orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from arbiscan.arbitrage import (
    ArbitrageEvaluation,
    ArbitrageMathError,
    build_opportunity,
    evaluate_market,
)
from arbiscan.domain import MarketId, OddsQuote, Opportunity, OpportunityId, Sport
from arbiscan.ingestion.collector import IngestionBatch, collect_snapshots
from arbiscan.marketbook import (
    CanonicalMarketBook,
    MarketBookDiagnostic,
    MarketBookDiagnosticCode,
    ProviderBookPolicy,
    build_market_books,
)
from arbiscan.matching.catalog import CanonicalRegistry
from arbiscan.normalization.strict import NormalizationIssue, normalize_source_snapshot
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.resilience import ProviderCallPolicy

Clock = Callable[[], datetime]


class BookIssueCode(StrEnum):
    """Compatibility reasons a canonical market could not be evaluated."""

    INCOMPLETE_MARKET = "incomplete_market"
    EVALUATION_REJECTED = "evaluation_rejected"


@dataclass(frozen=True, slots=True)
class BookIssue:
    """Compatibility diagnostic retained for the original vertical-slice API."""

    code: BookIssueCode
    market_id: MarketId
    detail: str


@dataclass(frozen=True, slots=True)
class VerticalSliceResult:
    """Complete provider-to-opportunity pipeline output."""

    ingestion: IngestionBatch
    quotes: tuple[OddsQuote, ...]
    normalization_issues: tuple[NormalizationIssue, ...]
    market_books: tuple[CanonicalMarketBook, ...]
    market_book_diagnostics: tuple[MarketBookDiagnostic, ...]
    evaluations: tuple[ArbitrageEvaluation, ...]
    opportunities: tuple[Opportunity, ...]
    book_issues: tuple[BookIssue, ...]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime, *, field_name: str = "as_of") -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _compatibility_book_issues(
    diagnostics: tuple[MarketBookDiagnostic, ...],
) -> list[BookIssue]:
    issues: list[BookIssue] = []
    for diagnostic in diagnostics:
        if diagnostic.market_id is None:
            continue
        if diagnostic.code is MarketBookDiagnosticCode.INCOMPLETE_MARKET:
            issues.append(
                BookIssue(
                    code=BookIssueCode.INCOMPLETE_MARKET,
                    market_id=diagnostic.market_id,
                    detail=diagnostic.detail,
                )
            )
        elif diagnostic.code is MarketBookDiagnosticCode.INSUFFICIENT_OUTCOMES:
            issues.append(
                BookIssue(
                    code=BookIssueCode.EVALUATION_REJECTED,
                    market_id=diagnostic.market_id,
                    detail=diagnostic.detail,
                )
            )
    return issues


async def run_vertical_slice(
    *,
    adapters: tuple[ProviderAdapter, ...],
    registry: CanonicalRegistry,
    sport: Sport,
    freshness_window: timedelta,
    as_of: datetime | None = None,
    clock: Clock = _utc_now,
    minimum_profit_margin: Decimal = Decimal("0"),
    provider_policy: ProviderCallPolicy | None = None,
    book_provider_policy: ProviderBookPolicy | None = None,
) -> VerticalSliceResult:
    """Run the provider-to-opportunity pipeline in live or replay mode.

    ``as_of=None`` is live mode: collection runs first and the evaluation timestamp
    is captured immediately afterwards. This guarantees newly ingested live data
    cannot be rejected merely because its ingestion timestamp is later than a
    timestamp sampled before network I/O.

    Passing an explicit ``as_of`` selects deterministic replay mode. In that mode
    the supplied historical timestamp remains authoritative and data ingested
    after it is correctly rejected by strict normalization.
    """
    fixed_as_of = None if as_of is None else _aware_utc(as_of)
    ingestion = await collect_snapshots(adapters, sport, policy=provider_policy)
    detected_at = _aware_utc(clock(), field_name="clock") if fixed_as_of is None else fixed_as_of

    normalized_quotes: list[OddsQuote] = []
    normalization_issues: list[NormalizationIssue] = []
    for ingested in ingestion.snapshots:
        normalized = normalize_source_snapshot(
            provider=ingested.provider,
            hooks=ingested.canonical_id_hooks,
            event=ingested.event,
            snapshot=ingested.snapshot,
            registry=registry,
            as_of=detected_at,
            freshness_window=freshness_window,
        )
        normalized_quotes.extend(normalized.quotes)
        normalization_issues.extend(normalized.issues)

    quotes = tuple(
        sorted(
            normalized_quotes,
            key=lambda quote: (
                quote.event_id.value,
                quote.market_id.value,
                quote.selection_id.value,
                quote.provider_id.value,
            ),
        )
    )

    market_scope = tuple(
        market.id
        for market in registry.markets
        if (event := registry.event(market.event_id)) is not None and event.sport is sport
    )
    market_book_batch = build_market_books(
        quotes,
        registry=registry,
        as_of=detected_at,
        freshness_window=freshness_window,
        provider_policy=book_provider_policy,
        market_ids=market_scope,
    )

    evaluations: list[ArbitrageEvaluation] = []
    opportunities: list[Opportunity] = []
    book_issues = _compatibility_book_issues(market_book_batch.diagnostics)

    for book in market_book_batch.books:
        try:
            evaluation = evaluate_market(
                book.quotes,
                book.expected_selection_ids,
                minimum_profit_margin=minimum_profit_margin,
            )
        except ArbitrageMathError as error:
            book_issues.append(
                BookIssue(
                    code=BookIssueCode.EVALUATION_REJECTED,
                    market_id=book.market.id,
                    detail=str(error),
                )
            )
            continue

        evaluations.append(evaluation)
        if evaluation.is_arbitrage:
            opportunities.append(
                build_opportunity(
                    evaluation,
                    opportunity_id=OpportunityId(
                        f"vertical-slice|{evaluation.event_id.value}|"
                        f"{evaluation.market_id.value}|{detected_at.isoformat()}"
                    ),
                    detected_at=detected_at,
                )
            )

    return VerticalSliceResult(
        ingestion=ingestion,
        quotes=quotes,
        normalization_issues=tuple(
            sorted(
                normalization_issues,
                key=lambda item: (
                    item.provider_id.value,
                    item.external_event_id,
                    item.code.value,
                    item.external_market_id or "",
                    item.external_selection_id or "",
                ),
            )
        ),
        market_books=market_book_batch.books,
        market_book_diagnostics=market_book_batch.diagnostics,
        evaluations=tuple(
            sorted(evaluations, key=lambda item: (item.event_id.value, item.market_id.value))
        ),
        opportunities=tuple(
            sorted(opportunities, key=lambda item: (item.event_id.value, item.market_id.value))
        ),
        book_issues=tuple(sorted(book_issues, key=lambda item: item.market_id.value)),
    )
