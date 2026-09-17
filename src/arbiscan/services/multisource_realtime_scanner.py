"""Phase-16 application scanner with overlap-safe multi-source live state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.domain import MarketId, OddsQuote, ProviderId, SelectionId, Sport
from arbiscan.ingestion.collector import IngestedSnapshot
from arbiscan.ingestion.multisource import ConsolidationDiagnostic, SourceObservationKey
from arbiscan.ingestion.multisource_state import MultiSourceLiveQuoteStore
from arbiscan.ingestion.realtime import (
    LiveQuoteStore,
    QuoteKey,
    RealtimeIngestionPolicy,
    RealtimeIngestionRuntime,
)
from arbiscan.marketbook import ProviderBookPolicy
from arbiscan.matching.catalog import CanonicalRegistry
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.services.observable_realtime_scanner import (
    RealtimeScanner as ObservableRealtimeScanner,
)
from arbiscan.services.realtime_scanner import RealtimeScanCycle

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
        minimum_profit_margin: Decimal = Decimal("0"),
        clock: Clock = _utc_now,
    ) -> None:
        resolved_policy = policy
        if resolved_policy is None:
            resolved_policy = runtime.policy if runtime is not None else RealtimeIngestionPolicy()
        resolved_store = store if store is not None else MultiSourceLiveQuoteStore(resolved_policy)
        super().__init__(
            adapters=adapters,
            registry=registry,
            sport=sport,
            policy=resolved_policy,
            runtime=runtime,
            store=resolved_store,
            book_provider_policy=book_provider_policy,
            minimum_profit_margin=minimum_profit_margin,
            clock=clock,
        )
        self._phase16_store = (
            resolved_store if isinstance(resolved_store, MultiSourceLiveQuoteStore) else None
        )
        self._phase16_cycles = 0
        self._phase16_equivalent_overlaps = 0
        self._phase16_material_conflicts = 0
        self._phase16_last_diagnostics: tuple[ConsolidationDiagnostic, ...] = ()
        self._phase16_last_equivalent_overlap_count = 0
        self._phase16_last_material_conflict_count = 0

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
        return cycle
