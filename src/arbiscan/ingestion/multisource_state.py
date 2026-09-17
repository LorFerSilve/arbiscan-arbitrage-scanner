"""Transport-aware live quote state for Phase 16 multi-source ingestion."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta

from arbiscan.domain import OddsQuote, ProviderId, QuoteStatus
from arbiscan.ingestion.multisource import (
    ConsolidationResult,
    SourceObservationKey,
    consolidate_quotes,
)
from arbiscan.ingestion.realtime import (
    LiveQuoteStore,
    QuoteStoreApplyResult,
    QuoteStoreDiagnostic,
    QuoteStoreEvictionResult,
    QuoteVersion,
    RealtimeIngestionPolicy,
)


class MultiSourceLiveQuoteStore(LiveQuoteStore):
    """Live state that versions each transport observation independently.

    The Phase-10 store remains the versioning implementation inside each transport
    domain. This wrapper prevents two independent feeds carrying the same bookmaker
    price from overwriting each other before Phase-16 consolidation.
    """

    def __init__(self, policy: RealtimeIngestionPolicy) -> None:
        super().__init__(policy)
        self._transport_stores: dict[ProviderId, LiveQuoteStore] = {}
        self._invalidated_observations: set[SourceObservationKey] = set()
        self._last_consolidation = ConsolidationResult(quotes=())

    def __len__(self) -> int:
        return sum(len(store) for store in self._transport_stores.values())

    @staticmethod
    def _transport_id(quote: OddsQuote) -> ProviderId:
        return quote.transport_provider_id or quote.provider_id

    @classmethod
    def _quote_sort_key(
        cls,
        quote: OddsQuote,
    ) -> tuple[str, str, str, str, str, datetime, datetime, str]:
        return (
            quote.event_id.value,
            quote.market_id.value,
            quote.selection_id.value,
            quote.provider_id.value,
            cls._transport_id(quote).value,
            quote.source_timestamp or quote.ingested_at,
            quote.ingested_at,
            quote.id.value,
        )

    @classmethod
    def _version_sort_key(
        cls,
        version: QuoteVersion,
    ) -> tuple[str, str, str, str, str, datetime, datetime, str]:
        return cls._quote_sort_key(version.quote)

    @property
    def last_consolidation_result(self) -> ConsolidationResult:
        """Return the most recent executable-slot consolidation decision."""
        return self._last_consolidation

    @property
    def invalidated_observations(self) -> tuple[SourceObservationKey, ...]:
        return tuple(
            sorted(
                self._invalidated_observations,
                key=lambda item: (
                    item.event_id.value,
                    item.market_id.value,
                    item.selection_id.value,
                    item.provider_id.value,
                    item.transport_provider_id.value,
                ),
            )
        )

    def invalidate_observations(self, keys: Iterable[SourceObservationKey]) -> None:
        """Suppress only the explicitly invalidated transport observations."""
        key_values = tuple(keys)
        if any(not isinstance(key, SourceObservationKey) for key in key_values):
            raise ValueError("keys must contain SourceObservationKey values")
        self._invalidated_observations.update(key_values)

    def apply(
        self,
        quotes: Iterable[OddsQuote],
        *,
        observed_at: datetime,
    ) -> QuoteStoreApplyResult:
        """Version quotes independently per transport and combine Phase-10 results."""
        quote_values = tuple(quotes)
        if any(not isinstance(quote, OddsQuote) for quote in quote_values):
            raise ValueError("quotes must contain OddsQuote values")

        grouped: dict[ProviderId, list[OddsQuote]] = defaultdict(list)
        for quote in quote_values:
            grouped[self._transport_id(quote)].append(quote)

        accepted: list[QuoteVersion] = []
        diagnostics: list[QuoteStoreDiagnostic] = []
        added_count = 0
        updated_count = 0
        duplicate_count = 0
        rejected_count = 0

        for transport_provider_id in sorted(grouped, key=lambda item: item.value):
            store = self._transport_stores.setdefault(
                transport_provider_id,
                LiveQuoteStore(self.policy),
            )
            result = store.apply(grouped[transport_provider_id], observed_at=observed_at)
            accepted.extend(result.accepted)
            diagnostics.extend(result.diagnostics)
            added_count += result.added_count
            updated_count += result.updated_count
            duplicate_count += result.duplicate_count
            rejected_count += result.rejected_count

            for version in result.accepted:
                if version.quote.status is QuoteStatus.ACTIVE:
                    self._invalidated_observations.discard(
                        SourceObservationKey.from_quote(version.quote)
                    )

        return QuoteStoreApplyResult(
            accepted=tuple(sorted(accepted, key=self._version_sort_key)),
            diagnostics=tuple(
                sorted(
                    diagnostics,
                    key=lambda item: (
                        item.key.event_id.value,
                        item.key.market_id.value,
                        item.key.selection_id.value,
                        item.key.provider_id.value,
                        item.code.value,
                        item.detail,
                    ),
                )
            ),
            added_count=added_count,
            updated_count=updated_count,
            duplicate_count=duplicate_count,
            rejected_count=rejected_count,
        )

    def fresh_versions(self, *, as_of: datetime) -> tuple[QuoteVersion, ...]:
        versions = (
            version
            for store in self._transport_stores.values()
            for version in store.fresh_versions(as_of=as_of)
            if SourceObservationKey.from_quote(version.quote) not in self._invalidated_observations
        )
        return tuple(sorted(versions, key=self._version_sort_key))

    def fresh_observations(self, *, as_of: datetime) -> tuple[OddsQuote, ...]:
        """Return all eligible transport observations before executable consolidation."""
        return tuple(version.quote for version in self.fresh_versions(as_of=as_of))

    def consolidate(self, *, as_of: datetime) -> ConsolidationResult:
        """Consolidate eligible observations to one executable quote per price slot."""
        result = consolidate_quotes(self.fresh_observations(as_of=as_of))
        self._last_consolidation = result
        return result

    def fresh_quotes(self, *, as_of: datetime) -> tuple[OddsQuote, ...]:
        """Return only executable, overlap-safe price-provider quotes."""
        return self.consolidate(as_of=as_of).quotes

    def stale_count(self, *, as_of: datetime) -> int:
        return sum(store.stale_count(as_of=as_of) for store in self._transport_stores.values())

    def maximum_quote_age(self, *, as_of: datetime) -> timedelta | None:
        observations = self.fresh_observations(as_of=as_of)
        if not observations:
            return None
        return max(as_of - (quote.source_timestamp or quote.ingested_at) for quote in observations)

    def evict_stale(self, *, as_of: datetime) -> QuoteStoreEvictionResult:
        evicted: list[QuoteVersion] = []
        diagnostics: list[QuoteStoreDiagnostic] = []

        for transport_provider_id in sorted(
            tuple(self._transport_stores), key=lambda item: item.value
        ):
            store = self._transport_stores[transport_provider_id]
            result = store.evict_stale(as_of=as_of)
            evicted.extend(result.evicted)
            diagnostics.extend(result.diagnostics)
            for version in result.evicted:
                self._invalidated_observations.discard(
                    SourceObservationKey.from_quote(version.quote)
                )
            if len(store) == 0:
                del self._transport_stores[transport_provider_id]

        return QuoteStoreEvictionResult(
            evicted=tuple(sorted(evicted, key=self._version_sort_key)),
            diagnostics=tuple(
                sorted(
                    diagnostics,
                    key=lambda item: (
                        item.key.event_id.value,
                        item.key.market_id.value,
                        item.key.selection_id.value,
                        item.key.provider_id.value,
                        item.code.value,
                        item.detail,
                    ),
                )
            ),
        )
