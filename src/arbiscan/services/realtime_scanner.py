"""Phase-10 live scanning orchestration over the realtime ingestion runtime."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.arbitrage import (
    ArbitrageEvaluation,
    ArbitrageMathError,
    build_opportunity,
    evaluate_market,
)
from arbiscan.domain import MarketId, OddsQuote, Opportunity, OpportunityId, Sport
from arbiscan.ingestion.realtime import (
    LiveQuoteStore,
    ProviderPollMetrics,
    QuoteStoreApplyResult,
    QuoteStoreDiagnosticCode,
    QuoteStoreEvictionResult,
    RealtimeIngestionBatch,
    RealtimeIngestionPolicy,
    RealtimeIngestionRuntime,
)
from arbiscan.marketbook import (
    CanonicalMarketBook,
    MarketBookDiagnostic,
    ProviderBookPolicy,
    build_market_books,
)
from arbiscan.matching.catalog import CanonicalRegistry
from arbiscan.normalization.strict import NormalizationIssue, normalize_source_snapshot
from arbiscan.providers.contract import ProviderAdapter

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class RealtimeEvaluationIssue:
    market_id: MarketId
    detail: str


@dataclass(frozen=True, slots=True)
class RealtimeCycleMetrics:
    """End-to-end measurable Phase-10 ingestion and detection metrics."""

    started_at: datetime
    detected_at: datetime
    provider_metrics: tuple[ProviderPollMetrics, ...]
    provider_issue_count: int
    normalization_issue_count: int
    accepted_quote_updates: int
    duplicate_quote_updates: int
    rejected_quote_updates: int
    current_fresh_quote_count: int
    stale_quote_count: int
    quote_age_max: timedelta | None
    ingestion_to_detection_latency_max: timedelta | None
    throttling_events: int
    market_book_count: int
    opportunity_count: int
    missed_poll_intervals_total: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "started_at",
            _aware_utc(self.started_at, field_name="started_at"),
        )
        object.__setattr__(
            self,
            "detected_at",
            _aware_utc(self.detected_at, field_name="detected_at"),
        )
        if self.detected_at < self.started_at:
            raise ValueError("detected_at cannot precede started_at")

    @property
    def provider_error_rate(self) -> Decimal:
        if not self.provider_metrics:
            return Decimal("0")
        providers_with_errors = sum(1 for metric in self.provider_metrics if metric.issue_count > 0)
        return Decimal(providers_with_errors) / Decimal(len(self.provider_metrics))

    @property
    def cycle_latency(self) -> timedelta:
        return self.detected_at - self.started_at


@dataclass(frozen=True, slots=True)
class RealtimeScanCycle:
    ingestion: RealtimeIngestionBatch
    normalization_issues: tuple[NormalizationIssue, ...]
    quote_updates: QuoteStoreApplyResult
    evictions: QuoteStoreEvictionResult
    fresh_quotes: tuple[OddsQuote, ...]
    market_books: tuple[CanonicalMarketBook, ...]
    market_book_diagnostics: tuple[MarketBookDiagnostic, ...]
    evaluations: tuple[ArbitrageEvaluation, ...]
    evaluation_issues: tuple[RealtimeEvaluationIssue, ...]
    opportunities: tuple[Opportunity, ...]
    metrics: RealtimeCycleMetrics


@dataclass(frozen=True, slots=True)
class PollScheduleState:
    cycle_number: int
    missed_intervals_total: int
    next_delay: timedelta


class RealtimeScanner:
    """Persistent live scanner whose quote state survives individual provider polls."""

    def __init__(
        self,
        *,
        adapters: tuple[ProviderAdapter, ...],
        registry: CanonicalRegistry,
        sport: Sport,
        policy: RealtimeIngestionPolicy | None = None,
        runtime: RealtimeIngestionRuntime | None = None,
        store: LiveQuoteStore | None = None,
        book_provider_policy: ProviderBookPolicy | None = None,
        minimum_profit_margin: Decimal = Decimal("0"),
        clock: Clock = _utc_now,
    ) -> None:
        if any(not isinstance(adapter, ProviderAdapter) for adapter in adapters):
            raise ValueError("adapters must contain ProviderAdapter values")
        if not isinstance(registry, CanonicalRegistry):
            raise ValueError("registry must be CanonicalRegistry")
        if not isinstance(sport, Sport):
            raise ValueError("sport must be Sport")
        if not callable(clock):
            raise ValueError("clock must be callable")
        self.policy = policy or RealtimeIngestionPolicy()
        self.runtime = runtime or RealtimeIngestionRuntime(policy=self.policy, clock=clock)
        if self.runtime.policy != self.policy:
            raise ValueError("runtime policy must equal scanner policy")
        self.store = store or LiveQuoteStore(self.policy)
        if self.store.policy != self.policy:
            raise ValueError("store policy must equal scanner policy")
        self.adapters = tuple(sorted(adapters, key=lambda item: item.provider.id.value))
        self.registry = registry
        self.sport = sport
        self.book_provider_policy = book_provider_policy
        self.minimum_profit_margin = minimum_profit_margin
        self._clock = clock
        self._missed_poll_intervals_total = 0

    def _now(self) -> datetime:
        return _aware_utc(self._clock(), field_name="clock")

    def _market_scope(self) -> tuple[MarketId, ...]:
        return tuple(
            market.id
            for market in self.registry.markets
            if (event := self.registry.event(market.event_id)) is not None
            and event.sport is self.sport
        )

    async def run_cycle(self) -> RealtimeScanCycle:
        """Poll, normalize, version, evict, align, and evaluate one live cycle."""
        started_at = self._now()
        ingestion = await self.runtime.poll_once(self.adapters, self.sport)
        detected_at = self._now()

        normalized_quotes: list[OddsQuote] = []
        normalization_issues: list[NormalizationIssue] = []
        for ingested in ingestion.ingestion.snapshots:
            normalized = normalize_source_snapshot(
                provider=ingested.provider,
                hooks=ingested.canonical_id_hooks,
                event=ingested.event,
                snapshot=ingested.snapshot,
                registry=self.registry,
                as_of=detected_at,
                freshness_window=self.policy.freshness_window,
            )
            normalized_quotes.extend(normalized.quotes)
            normalization_issues.extend(normalized.issues)

        quote_updates = self.store.apply(normalized_quotes, observed_at=detected_at)
        stale_before_eviction = sum(
            1
            for version in self.store.fresh_versions(as_of=detected_at)
            if detected_at - version.effective_timestamp > self.policy.freshness_window
        )
        evictions = self.store.evict_stale(as_of=detected_at)
        stale_evicted = sum(
            1
            for diagnostic in evictions.diagnostics
            if diagnostic.code is QuoteStoreDiagnosticCode.STALE_EVICTED
        )
        fresh_quotes = self.store.fresh_quotes(as_of=detected_at)

        market_batch = build_market_books(
            fresh_quotes,
            registry=self.registry,
            as_of=detected_at,
            freshness_window=self.policy.freshness_window,
            provider_policy=self.book_provider_policy,
            market_ids=self._market_scope(),
        )

        evaluations: list[ArbitrageEvaluation] = []
        evaluation_issues: list[RealtimeEvaluationIssue] = []
        opportunities: list[Opportunity] = []
        for book in market_batch.books:
            try:
                evaluation = evaluate_market(
                    book.quotes,
                    book.expected_selection_ids,
                    minimum_profit_margin=self.minimum_profit_margin,
                )
            except ArbitrageMathError as error:
                evaluation_issues.append(
                    RealtimeEvaluationIssue(market_id=book.market.id, detail=str(error))
                )
                continue
            evaluations.append(evaluation)
            if evaluation.is_arbitrage:
                opportunities.append(
                    build_opportunity(
                        evaluation,
                        opportunity_id=OpportunityId(
                            f"realtime|{evaluation.event_id.value}|"
                            f"{evaluation.market_id.value}|{detected_at.isoformat()}"
                        ),
                        detected_at=detected_at,
                    )
                )

        ingestion_latency = self._maximum_ingestion_to_detection_latency(
            fresh_quotes,
            detected_at=detected_at,
        )
        metrics = RealtimeCycleMetrics(
            started_at=started_at,
            detected_at=detected_at,
            provider_metrics=ingestion.provider_metrics,
            provider_issue_count=len(ingestion.ingestion.issues),
            normalization_issue_count=len(normalization_issues),
            accepted_quote_updates=len(quote_updates.accepted),
            duplicate_quote_updates=quote_updates.duplicate_count,
            rejected_quote_updates=quote_updates.rejected_count,
            current_fresh_quote_count=len(fresh_quotes),
            stale_quote_count=stale_before_eviction + stale_evicted,
            quote_age_max=self.store.maximum_quote_age(as_of=detected_at),
            ingestion_to_detection_latency_max=ingestion_latency,
            throttling_events=ingestion.throttling_events,
            market_book_count=len(market_batch.books),
            opportunity_count=len(opportunities),
            missed_poll_intervals_total=self._missed_poll_intervals_total,
        )

        return RealtimeScanCycle(
            ingestion=ingestion,
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
            quote_updates=quote_updates,
            evictions=evictions,
            fresh_quotes=fresh_quotes,
            market_books=market_batch.books,
            market_book_diagnostics=market_batch.diagnostics,
            evaluations=tuple(
                sorted(evaluations, key=lambda item: (item.event_id.value, item.market_id.value))
            ),
            evaluation_issues=tuple(
                sorted(evaluation_issues, key=lambda item: item.market_id.value)
            ),
            opportunities=tuple(
                sorted(opportunities, key=lambda item: (item.event_id.value, item.market_id.value))
            ),
            metrics=metrics,
        )

    @staticmethod
    def _maximum_ingestion_to_detection_latency(
        quotes: tuple[OddsQuote, ...],
        *,
        detected_at: datetime,
    ) -> timedelta | None:
        if not quotes:
            return None
        return max(detected_at - quote.ingested_at for quote in quotes)

    async def cycles(self, *, sleep: Sleep = asyncio.sleep) -> AsyncIterator[RealtimeScanCycle]:
        """Yield non-overlapping polling cycles with explicit no-backlog backpressure."""
        cycle_number = 0
        while True:
            cycle_started_at = self._now()
            result = await self.run_cycle()
            cycle_number += 1
            yield result

            elapsed = self._now() - cycle_started_at
            interval = self.policy.poll_interval
            if elapsed < interval:
                await sleep((interval - elapsed).total_seconds())
                continue

            missed = int(elapsed.total_seconds() // interval.total_seconds())
            self._missed_poll_intervals_total += max(1, missed)

    def schedule_state(self, *, cycle_number: int, cycle_started_at: datetime) -> PollScheduleState:
        """Expose deterministic scheduler state for observability/tests."""
        if type(cycle_number) is not int or cycle_number < 0:
            raise ValueError("cycle_number must be a non-negative integer")
        started = _aware_utc(cycle_started_at, field_name="cycle_started_at")
        elapsed = self._now() - started
        if elapsed < timedelta(0):
            raise ValueError("cycle_started_at cannot be in the future")
        remaining = self.policy.poll_interval - elapsed
        return PollScheduleState(
            cycle_number=cycle_number,
            missed_intervals_total=self._missed_poll_intervals_total,
            next_delay=max(timedelta(0), remaining),
        )
