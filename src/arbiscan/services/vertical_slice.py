"""Phase 5 network-free ingestion-to-opportunity orchestration."""

from __future__ import annotations

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
from arbiscan.matching.catalog import CanonicalRegistry
from arbiscan.normalization.strict import NormalizationIssue, normalize_source_snapshot
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.resilience import ProviderCallPolicy


class BookIssueCode(StrEnum):
    """Reasons a canonical Phase 5 market could not be evaluated."""

    INCOMPLETE_MARKET = "incomplete_market"
    EVALUATION_REJECTED = "evaluation_rejected"


@dataclass(frozen=True, slots=True)
class BookIssue:
    """Fail-closed diagnostic for a canonical market-book construction attempt."""

    code: BookIssueCode
    market_id: MarketId
    detail: str


@dataclass(frozen=True, slots=True)
class VerticalSliceResult:
    """Complete deterministic Phase 5 pipeline output."""

    ingestion: IngestionBatch
    quotes: tuple[OddsQuote, ...]
    normalization_issues: tuple[NormalizationIssue, ...]
    evaluations: tuple[ArbitrageEvaluation, ...]
    opportunities: tuple[Opportunity, ...]
    book_issues: tuple[BookIssue, ...]


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)


def _best_quote(candidates: tuple[OddsQuote, ...]) -> OddsQuote:
    return max(
        candidates,
        key=lambda quote: (
            quote.decimal_price,
            quote.provider_id.value,
            quote.id.value,
        ),
    )


async def run_vertical_slice(
    *,
    adapters: tuple[ProviderAdapter, ...],
    registry: CanonicalRegistry,
    sport: Sport,
    as_of: datetime,
    freshness_window: timedelta,
    minimum_profit_margin: Decimal = Decimal("0"),
    provider_policy: ProviderCallPolicy | None = None,
) -> VerticalSliceResult:
    """Run the first deterministic provider-to-opportunity pipeline."""
    detected_at = _aware_utc(as_of)
    ingestion = await collect_snapshots(adapters, sport, policy=provider_policy)

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

    evaluations: list[ArbitrageEvaluation] = []
    opportunities: list[Opportunity] = []
    book_issues: list[BookIssue] = []

    for market in sorted(registry.markets, key=lambda value: value.id.value):
        event = registry.event(market.event_id)
        if event is None or event.sport is not sport:
            continue

        expected = registry.selection_ids_for_market(market.id)
        best_quotes: list[OddsQuote] = []
        missing: list[str] = []

        for selection_id in expected:
            candidates = tuple(
                quote
                for quote in quotes
                if quote.market_id == market.id and quote.selection_id == selection_id
            )
            if not candidates:
                missing.append(selection_id.value)
                continue
            best_quotes.append(_best_quote(candidates))

        if missing:
            book_issues.append(
                BookIssue(
                    code=BookIssueCode.INCOMPLETE_MARKET,
                    market_id=market.id,
                    detail=f"missing canonical selections: {sorted(missing)}",
                )
            )
            continue

        try:
            evaluation = evaluate_market(
                best_quotes,
                expected,
                minimum_profit_margin=minimum_profit_margin,
            )
        except ArbitrageMathError as error:
            book_issues.append(
                BookIssue(
                    code=BookIssueCode.EVALUATION_REJECTED,
                    market_id=market.id,
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
                        f"phase5|{evaluation.event_id.value}|{evaluation.market_id.value}|"
                        f"{detected_at.isoformat()}"
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
        evaluations=tuple(
            sorted(evaluations, key=lambda item: (item.event_id.value, item.market_id.value))
        ),
        opportunities=tuple(
            sorted(opportunities, key=lambda item: (item.event_id.value, item.market_id.value))
        ),
        book_issues=tuple(sorted(book_issues, key=lambda item: item.market_id.value)),
    )
