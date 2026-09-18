"""Phase-16 application scanner with overlap-safe multi-source live state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.domain import MarketId, OddsQuote, ProviderId, SelectionId, Sport
from arbiscan.ingestion.collector import IngestedSnapshot
from arbiscan.ingestion.multisource import (
    ConsolidationDiagnostic,
    ConsolidationDiagnosticCode,
    SourceObservationKey,
)
from arbiscan.ingestion.multisource_state import MultiSourceLiveQuoteStore
from arbiscan.ingestion.realtime import (
    LiveQuoteStore,
    ProviderIngestionHealth,
    ProviderPollMetrics,
    QuoteKey,
    RealtimeIngestionPolicy,
    RealtimeIngestionRuntime,
)
from arbiscan.marketbook import ProviderBookPolicy
from arbiscan.matching.catalog import CanonicalRegistry
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.models import ProviderHealthState
from arbiscan.services.observable_realtime_scanner import (
    RealtimeScanner as ObservableRealtimeScanner,
)
from arbiscan.services.realtime_scanner import RealtimeScanCycle
from arbiscan.services.source_enablement import TransportSourceEnablementPolicy

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _source_status_is_active(value: str) -> bool:
    return value.strip().casefold() == "active"


@dataclass(frozen=True, slots=True)
class MultiSourceTelemetrySnapshot:
    """Cumulative and last-cycle Phase-16 overlap/conflict telemetry."""

    cycles: int
    equivalent_overlaps: int
    material_conflicts: int
    last_equivalent_overlap_count: int
    last_material_conflict_count: int
    last_diagnostics: tuple[ConsolidationDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class SourceOperationalSnapshot:
    """Latest cumulative/current operational view for one transport source."""

    provider_id: ProviderId
    health_state: ProviderHealthState
    available: bool
    request_count: int
    error_count: int
    rate_limit_event_count: int
    rate_limit_remaining: int | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_update_at: datetime | None
    update_interval: timedelta | None
    consecutive_failures: int
    last_issue_count: int
    fresh_observation_count: int
    fresh_observation_age_seconds: tuple[float, ...]
    normalization_failure_count: int
    matching_failure_count: int
    overlap_diagnostic_count: int
    material_conflict_count: int


@dataclass(frozen=True, slots=True)
class MultiSourceOperationalSnapshot:
    """Operational state exposed after each completed multi-source scan cycle."""

    observed_at: datetime
    poll_interval: timedelta
    max_concurrency: int
    sources: tuple[SourceOperationalSnapshot, ...]


class RealtimeScanner(ObservableRealtimeScanner):
    """Application scanner that keeps transport and executable provider identity separate."""

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
        source_enablement_policy: TransportSourceEnablementPolicy | None = None,
        minimum_profit_margin: Decimal = Decimal("0"),
        clock: Clock = _utc_now,
    ) -> None:
        configured_adapters = tuple(adapters)
        enabled_adapters = (
            configured_adapters
            if source_enablement_policy is None
            else source_enablement_policy.select(configured_adapters)
        )
        resolved_policy = policy
        if resolved_policy is None:
            resolved_policy = runtime.policy if runtime is not None else RealtimeIngestionPolicy()
        resolved_store = store if store is not None else MultiSourceLiveQuoteStore(resolved_policy)
        super().__init__(
            adapters=enabled_adapters,
            registry=registry,
            sport=sport,
            policy=resolved_policy,
            runtime=runtime,
            store=resolved_store,
            book_provider_policy=book_provider_policy,
            minimum_profit_margin=minimum_profit_margin,
            clock=clock,
        )
        self._configured_transport_provider_ids = tuple(
            sorted(
                (adapter.provider.id for adapter in configured_adapters),
                key=lambda value: value.value,
            )
        )
        self._source_enablement_policy = source_enablement_policy
        self._phase16_store = (
            resolved_store if isinstance(resolved_store, MultiSourceLiveQuoteStore) else None
        )
        self._phase16_cycles = 0
        self._phase16_equivalent_overlaps = 0
        self._phase16_material_conflicts = 0
        self._phase16_last_diagnostics: tuple[ConsolidationDiagnostic, ...] = ()
        self._phase16_last_equivalent_overlap_count = 0
        self._phase16_last_material_conflict_count = 0
        self._phase16_overlap_diagnostics_by_provider: dict[ProviderId, int] = {}
        self._phase16_material_conflicts_by_provider: dict[ProviderId, int] = {}
        self._phase16_operational_snapshot: MultiSourceOperationalSnapshot | None = None

    @property
    def configured_transport_provider_ids(self) -> tuple[ProviderId, ...]:
        """Return every transport supplied to the scanner before enablement filtering."""
        return self._configured_transport_provider_ids

    @property
    def enabled_transport_provider_ids(self) -> tuple[ProviderId, ...]:
        """Return the transport sources that are actually eligible to be polled."""
        return tuple(adapter.provider.id for adapter in self.adapters)

    @property
    def source_enablement_policy(self) -> TransportSourceEnablementPolicy | None:
        """Return the explicit staged-enable policy, when one was supplied."""
        return self._source_enablement_policy

    @property
    def multisource_store(self) -> MultiSourceLiveQuoteStore | None:
        """Return the transport-aware store when Phase-16 state management is active."""
        return self._phase16_store

    @property
    def multisource_telemetry(self) -> MultiSourceTelemetrySnapshot:
        return MultiSourceTelemetrySnapshot(
            cycles=self._phase16_cycles,
            equivalent_overlaps=self._phase16_equivalent_overlaps,
            material_conflicts=self._phase16_material_conflicts,
            last_equivalent_overlap_count=self._phase16_last_equivalent_overlap_count,
            last_material_conflict_count=self._phase16_last_material_conflict_count,
            last_diagnostics=self._phase16_last_diagnostics,
        )

    @property
    def operational_snapshot(self) -> MultiSourceOperationalSnapshot | None:
        """Return the latest per-source operational snapshot, if a cycle has completed."""
        return self._phase16_operational_snapshot

    def _explicit_inactive_quote_keys(self, ingested: IngestedSnapshot) -> set[QuoteKey]:
        """Invalidate the reporting transport while preserving Phase-10 cycle compatibility."""
        store = self._phase16_store
        if store is None:
            return super()._explicit_inactive_quote_keys(ingested)

        hooks = ingested.canonical_id_hooks
        if hooks is None:
            return set()
        event_id = hooks.event_id(ingested.event)
        canonical_event = None if event_id is None else self.registry.event(event_id)
        if event_id is None or canonical_event is None:
            return set()

        invalidated: set[SourceObservationKey] = set()
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
                invalidated.update(
                    self._observation_key(
                        transport_provider_id=ingested.provider.id,
                        provider_id=quote_provider.id,
                        event_id=event_id,
                        market_id=market_id,
                        selection_id=selection.id,
                    )
                    for selection in self.registry.selections
                    if selection.market_id == market_id
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
                invalidated.add(
                    self._observation_key(
                        transport_provider_id=ingested.provider.id,
                        provider_id=quote_provider.id,
                        event_id=event_id,
                        market_id=market_id,
                        selection_id=selection_id,
                    )
                )

        store.invalidate_observations(invalidated)
        return {
            QuoteKey(
                provider_id=key.provider_id,
                event_id=key.event_id,
                market_id=key.market_id,
                selection_id=key.selection_id,
            )
            for key in invalidated
        }

    def _update_source_invalidations(
        self,
        normalized_quotes: tuple[OddsQuote, ...],
        explicit_invalidations: set[QuoteKey],
    ) -> None:
        """Keep transport invalidations in the multi-source store, not bookmaker-global state."""
        if self._phase16_store is None:
            super()._update_source_invalidations(normalized_quotes, explicit_invalidations)

    @staticmethod
    def _observation_key(
        *,
        transport_provider_id: ProviderId,
        provider_id: ProviderId,
        event_id: object,
        market_id: MarketId,
        selection_id: SelectionId,
    ) -> SourceObservationKey:
        from arbiscan.domain import EventId

        if not isinstance(event_id, EventId):
            raise ValueError("event_id must be EventId")
        return SourceObservationKey(
            transport_provider_id=transport_provider_id,
            provider_id=provider_id,
            event_id=event_id,
            market_id=market_id,
            selection_id=selection_id,
        )

    def _cycle_log_fields(
        self,
        cycle: RealtimeScanCycle,
    ) -> dict[str, str | int | float | bool | None]:
        fields = super()._cycle_log_fields(cycle)
        store = self._phase16_store
        if store is None:
            return fields

        consolidation = store.last_consolidation_result
        diagnostic_codes = ",".join(
            diagnostic.code.value for diagnostic in consolidation.diagnostics
        )
        transport_provider_ids = ";".join(
            ",".join(provider_id.value for provider_id in diagnostic.transport_provider_ids)
            for diagnostic in consolidation.diagnostics
        )
        fields.update(
            {
                "fresh_observation_count": len(
                    store.fresh_observations(as_of=cycle.metrics.detected_at)
                ),
                "executable_quote_count": len(consolidation.quotes),
                "equivalent_overlap_count": consolidation.equivalent_overlap_count,
                "material_conflict_count": consolidation.conflict_count,
                "diagnostic_codes": diagnostic_codes,
                "transport_provider_ids": transport_provider_ids,
            }
        )
        return fields

    @staticmethod
    def _health_by_provider(
        values: tuple[ProviderIngestionHealth, ...],
    ) -> dict[ProviderId, ProviderIngestionHealth]:
        return {value.provider_id: value for value in values}

    @staticmethod
    def _poll_by_provider(
        values: tuple[ProviderPollMetrics, ...],
    ) -> dict[ProviderId, ProviderPollMetrics]:
        return {value.provider_id: value for value in values}

    def _build_operational_snapshot(
        self,
        cycle: RealtimeScanCycle,
    ) -> MultiSourceOperationalSnapshot:
        store = self._phase16_store
        if store is None:
            raise RuntimeError("multi-source operational snapshot requires multi-source store")

        metrics = self.metrics_registry.snapshot()
        health_by_provider = self._health_by_provider(cycle.ingestion.provider_health)
        poll_by_provider = self._poll_by_provider(cycle.metrics.provider_metrics)

        ages_by_provider: dict[ProviderId, list[float]] = {}
        for quote in store.fresh_observations(as_of=cycle.metrics.detected_at):
            provider_id = quote.transport_provider_id or quote.provider_id
            effective_at = quote.source_timestamp or quote.ingested_at
            age_seconds = (cycle.metrics.detected_at - effective_at).total_seconds()
            ages_by_provider.setdefault(provider_id, []).append(age_seconds)

        provider_ids = (
            {adapter.provider.id for adapter in self.adapters}
            | set(health_by_provider)
            | set(poll_by_provider)
            | set(ages_by_provider)
        )

        sources: list[SourceOperationalSnapshot] = []
        for provider_id in sorted(provider_ids, key=lambda value: value.value):
            health = health_by_provider.get(provider_id)
            poll = poll_by_provider.get(provider_id)
            health_state = ProviderHealthState.UNAVAILABLE if health is None else health.state
            ages = tuple(sorted(ages_by_provider.get(provider_id, [])))
            sources.append(
                SourceOperationalSnapshot(
                    provider_id=provider_id,
                    health_state=health_state,
                    available=metrics.provider_available.get(
                        provider_id,
                        health_state is not ProviderHealthState.UNAVAILABLE,
                    ),
                    request_count=metrics.provider_requests.get(provider_id, 0),
                    error_count=metrics.provider_errors.get(provider_id, 0),
                    rate_limit_event_count=metrics.rate_limit_events.get(provider_id, 0),
                    rate_limit_remaining=None if poll is None else poll.rate_limit_remaining,
                    last_attempt_at=None if health is None else health.last_attempt_at,
                    last_success_at=None if health is None else health.last_success_at,
                    last_update_at=None if health is None else health.last_update_at,
                    update_interval=None if poll is None else poll.update_interval,
                    consecutive_failures=0 if health is None else health.consecutive_failures,
                    last_issue_count=0 if health is None else health.last_issue_count,
                    fresh_observation_count=len(ages),
                    fresh_observation_age_seconds=ages,
                    normalization_failure_count=metrics.provider_normalization_failures.get(
                        provider_id,
                        0,
                    ),
                    matching_failure_count=metrics.provider_matching_failures.get(
                        provider_id,
                        0,
                    ),
                    overlap_diagnostic_count=self._phase16_overlap_diagnostics_by_provider.get(
                        provider_id,
                        0,
                    ),
                    material_conflict_count=self._phase16_material_conflicts_by_provider.get(
                        provider_id,
                        0,
                    ),
                )
            )

        return MultiSourceOperationalSnapshot(
            observed_at=cycle.metrics.detected_at,
            poll_interval=self.policy.poll_interval,
            max_concurrency=self.policy.max_concurrency,
            sources=tuple(sources),
        )

    async def run_cycle(self) -> RealtimeScanCycle:
        cycle = await super().run_cycle()
        store = self._phase16_store
        if store is None:
            return cycle

        consolidation = store.last_consolidation_result
        self._phase16_cycles += 1
        self._phase16_equivalent_overlaps += consolidation.equivalent_overlap_count
        self._phase16_material_conflicts += consolidation.conflict_count
        self._phase16_last_equivalent_overlap_count = consolidation.equivalent_overlap_count
        self._phase16_last_material_conflict_count = consolidation.conflict_count
        self._phase16_last_diagnostics = consolidation.diagnostics

        for diagnostic in consolidation.diagnostics:
            for provider_id in diagnostic.transport_provider_ids:
                self._phase16_overlap_diagnostics_by_provider[provider_id] = (
                    self._phase16_overlap_diagnostics_by_provider.get(provider_id, 0) + 1
                )
                if diagnostic.code is ConsolidationDiagnosticCode.MATERIAL_CONFLICT:
                    self._phase16_material_conflicts_by_provider[provider_id] = (
                        self._phase16_material_conflicts_by_provider.get(provider_id, 0) + 1
                    )

        self._phase16_operational_snapshot = self._build_operational_snapshot(cycle)
        return cycle
