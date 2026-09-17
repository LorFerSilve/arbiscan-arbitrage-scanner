"""Realtime scanning orchestration with Phase-16 multi-source quote consolidation."""

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
from arbiscan.ingestion.collector import IngestedSnapshot
from arbiscan.ingestion.multisource import (
    MultiSourceQuoteStore,
    QuoteConsolidationDiagnostic,
    SourceQuoteKey,
    SourceQuoteStoreApplyResult,
    SourceQuoteStoreDiagnosticCode,
    SourceQuoteStoreEvictionResult,
)
from arbiscan.ingestion.realtime import (
    ProviderPollMetrics,
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


def _source_status_is_active(value: str) -> bool:
    return value.strip().casefold() == "active"


def _quote_key_sort(key: SourceQuoteKey) -> tuple[str, str, str, str, str]:
    return (
        key.provider_id.value,
        key.transport_provider_id.value,
        key.event_id.value,
        key.market_id.value,
        key.selection_id.value,
    )


@dataclass(frozen=True, slots=True)
class RealtimeEvaluationIssue:
    market_id: MarketId
    detail: str


@dataclass(frozen=True, slots=True)
class RealtimeCycleMetrics:
    """End-to-end measurable realtime ingestion and detection metrics."""

    started_at: datetime
    detected_at: datetime
    provider_metrics: tuple[ProviderPollMetrics, ...]
    provider_issue_count: int
    normalization_issue_count: int
    accepted_quote_updates: int
    duplicate_quote_updates: int
    rejected_quote_updates: int
    source_invalidated_quote_count: int
    current_fresh_quote_count: int
    stale_quote_count: int
    quote_age_max: timedelta | None
    ingestion_to_detection_latency_max: timedelta | None
    throttling_events: int
    market_book_count: int
    opportunity_count: int
    missed_poll_intervals_total: int
    source_conflict_count: int = 0
    equivalent_source_observation_count: int = 0

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
    quote_updates: SourceQuoteStoreApplyResult
    evictions: SourceQuoteStoreEvictionResult
    source_invalidated_quote_keys: tuple[SourceQuoteKey, ...]
    fresh_quotes: tuple[OddsQuote, ...]
    market_books: tuple[CanonicalMarketBook, ...]
    market_book_diagnostics: tuple[MarketBookDiagnostic, ...]
    evaluations: tuple[ArbitrageEvaluation, ...]
    evaluation_issues: tuple[RealtimeEvaluationIssue, ...]
    opportunities: tuple[Opportunity, ...]
    metrics: RealtimeCycleMetrics
    consolidation_diagnostics: tuple[QuoteConsolidationDiagnostic, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True, slots=True)
class PollScheduleState:
    cycle_number: int
    missed_intervals_total: int
    next_delay: timedelta


class RealtimeScanner:
    """Persistent live scanner whose source-aware quote state survives provider polls."""

    def __init__(
        self,
        *,
        adapters: tuple[ProviderAdapter, ...],
        registry: CanonicalRegistry,
        sport: Sport,
        policy: RealtimeIngestionPolicy | None = None,
        runtime: RealtimeIngestionRuntime | None = None,
        store: MultiSourceQuoteStore | None = None,
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
        self.store = store or MultiSourceQuoteStore(self.policy)
        if self.store.policy != self.policy:
            raise ValueError("store policy must equal scanner policy")
        self.adapters = tuple(sorted(adapters, key=lambda item: item.provider.id.value))
        self.registry = registry
        self.sport = sport
        self.book_provider_policy = book_provider_policy
        self.minimum_profit_margin = minimum_profit_margin
        self._clock = clock
        self._missed_poll_intervals_total = 0
        self._source_invalidated_quote_keys: set[SourceQuoteKey] = set()

    def _now(self) -> datetime:
        return _aware_utc(self._clock(), field_name="clock")

    def _market_scope(self) -> tuple[MarketId, ...]:
        return tuple(
            market.id
            for market in self.registry.markets
            if (event := self.registry.event(market.event_id)) is not None
            and event.sport is self.sport
        )

    def _explicit_inactive_quote_keys(self, ingested: IngestedSnapshot) -> set[SourceQuoteKey]:
        hooks = ingested.canonical_id_hooks
        if hooks is None:
            return set()
        event_id = hooks.event_id(ingested.event)
        canonical_event = None if event_id is None else self.registry.event(event_id)
        if event_id is None or canonical_event is None:
            return set()

        keys: set[SourceQuoteKey] = set()
        for market in ingested.snapshot.markets:
            market_id = hooks.market_id(market)
            canonical_market = None if market_id is None else self.registry.market(market_id)
            if (
                market_id is None
                or canonical_market is None
                or canonical_market.event_id != event_id
            ):
                continue

            quote_provider = market.price_provider or ingested.provider
            if not _source_status_is_active(market.source_status):
                for selection in self.registry.selections:
                    if selection.market_id == market_id:
                        keys.add(
                            SourceQuoteKey(
                                transport_provider_id=ingested.provider.id,
                                provider_id=quote_provider.id,
                                event_id=event_id,
                                market_id=market_id,
                                selection_id=selection.id,
                            )
                        )
                continue

            for source_selection in market.selections:
                if _source_status_is_active(source_selection.source_status):
                    continue
                selection_id = hooks.selection_id(market, source_selection)
                canonical_selection = (
                    None if selection_id is None else self.registry.selection(selection_id)
                )
                if (
                    selection_id is None
                    or canonical_selection is None
                    or canonical_selection.market_id != market_id
                ):
                    continue
                keys.add(
                    SourceQuoteKey(
                        transport_provider_id=ingested.provider.id,
                        provider_id=quote_provider.id,
                        event_id=event_id,
                        market_id=market_id,
                        selection_id=selection_id,
                    )
                )
        return keys

    async def run_cycle(self) -> RealtimeScanCycle:
        """Poll, normalize, source-version, consolidate, align, and evaluate one cycle."""
        started_at = self._now()
        ingestion = await self.runtime.poll_once(self.adapters, self.sport)
        detected_at = self._now()
        normalization_as_of = detected_at + self.policy.clock_skew_tolerance

        normalized_quotes: list[OddsQuote] = []
        normalization_issues: list[NormalizationIssue] = []
        explicit_invalidations: set[SourceQuoteKey] = set()
        for ingested in ingestion.ingestion.snapshots:
            explicit_invalidations.update(self._explicit_inactive_quote_keys(ingested))
            normalized = normalize_source_snapshot(
                provider=ingested.provider,
                hooks=ingested.canonical_id_hooks,
                event=ingested.event,
                snapshot=ingested.snapshot,
                registry=self.registry,
                as_of=normalization_as_of,
                freshness_window=self.policy.freshness_window,
            )
            normalized_quotes.extend(normalized.quotes)
            normalization_issues.extend(normalized.issues)

        quote_updates = self.store.apply(normalized_quotes, observed_at=detected_at)
        active_observed_keys = {SourceQuoteKey.from_quote(quote) for quote in normalized_quotes}
        self._source_invalidated_quote_keys.difference_update(active_observed_keys)
        self._source_invalidated_quote_keys.update(explicit_invalidations)

        evictions = self.store.evict_stale(as_of=detected_at)
        for version in evictions.evicted:
            self._source_invalidated_quote_keys.discard(version.key)
        stale_evicted = sum(
            1
            for diagnostic in evictions.diagnostics
            if diagnostic.code is SourceQuoteStoreDiagnosticCode.STALE_EVICTED
        )

        consolidation = self.store.consolidate_fresh(
            as_of=detected_at,
            excluded_keys=self._source_invalidated_quote_keys,
        )
        fresh_quotes = consolidation.quotes

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

        metrics = RealtimeCycleMetrics(
            started_at=started_at,
            detected_at=detected_at,
            provider_metrics=ingestion.provider_metrics,
            provider_issue_count=len(ingestion.ingestion.issues),
            normalization_issue_count=len(normalization_issues),
            accepted_quote_updates=len(quote_updates.accepted),
            duplicate_quote_updates=quote_updates.duplicate_count,
            rejected_quote_updates=quote_updates.rejected_count,
            source_invalidated_quote_count=len(explicit_invalidations),
            current_fresh_quote_count=len(fresh_quotes),
            stale_quote_count=stale_evicted,
            quote_age_max=self._maximum_quote_age(fresh_quotes, as_of=detected_at),
            ingestion_to_detection_latency_max=self._maximum_ingestion_to_detection_latency(
                fresh_quotes,
                detected_at=detected_at,
            ),
            throttling_events=ingestion.throttling_events,
            market_book_count=len(market_batch.books),
            opportunity_count=len(opportunities),
            missed_poll_intervals_total=self._missed_poll_intervals_total,
            source_conflict_count=consolidation.conflict_count,
            equivalent_source_observation_count=consolidation.equivalent_overlap_count,
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
            source_invalidated_quote_keys=tuple(
                sorted(explicit_invalidations, key=_quote_key_sort)
            ),
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
            consolidation_diagnostics=consolidation.diagnostics,
        )

    @staticmethod
    def _maximum_quote_age(
        quotes: tuple[OddsQuote, ...],
        *,
        as_of: datetime,
    ) -> timedelta | None:
        if not quotes:
            return None
        return max(as_of - (quote.source_timestamp or quote.ingested_at) for quote in quotes)

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
        while True:
            cycle_started_at = self._now()
            result = await self.run_cycle()
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
