"""Phase-16 source-aware live quote state and deterministic overlap consolidation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from arbiscan.domain import EventId, MarketId, OddsQuote, ProviderId, QuoteStatus, SelectionId
from arbiscan.ingestion.realtime import RealtimeIngestionPolicy


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _transport_provider_id(quote: OddsQuote) -> ProviderId:
    provider_id = quote.transport_provider_id
    if provider_id is None:
        raise ValueError("validated OddsQuote must expose transport_provider_id")
    return provider_id


@dataclass(frozen=True, slots=True, order=True)
class SourceQuoteKey:
    """Identity of one live observation from one transport source."""

    transport_provider_id: ProviderId
    provider_id: ProviderId
    event_id: EventId
    market_id: MarketId
    selection_id: SelectionId

    @classmethod
    def from_quote(cls, quote: OddsQuote) -> SourceQuoteKey:
        return cls(
            transport_provider_id=_transport_provider_id(quote),
            provider_id=quote.provider_id,
            event_id=quote.event_id,
            market_id=quote.market_id,
            selection_id=quote.selection_id,
        )


@dataclass(frozen=True, slots=True, order=True)
class PriceSlotKey:
    """Executable bookmaker/selection slot shared by overlapping transports."""

    provider_id: ProviderId
    event_id: EventId
    market_id: MarketId
    selection_id: SelectionId

    @classmethod
    def from_quote(cls, quote: OddsQuote) -> PriceSlotKey:
        return cls(
            provider_id=quote.provider_id,
            event_id=quote.event_id,
            market_id=quote.market_id,
            selection_id=quote.selection_id,
        )


@dataclass(frozen=True, slots=True)
class SourceQuoteVersion:
    key: SourceQuoteKey
    revision: int
    quote: OddsQuote
    observed_at: datetime

    def __post_init__(self) -> None:
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("quote revision must be an integer >= 1")
        if not isinstance(self.quote, OddsQuote):
            raise ValueError("quote version quote must be OddsQuote")
        if self.key != SourceQuoteKey.from_quote(self.quote):
            raise ValueError("quote version key must match source-aware quote identity")
        object.__setattr__(
            self,
            "observed_at",
            _aware_utc(self.observed_at, field_name="quote_version.observed_at"),
        )

    @property
    def effective_timestamp(self) -> datetime:
        return self.quote.source_timestamp or self.quote.ingested_at


class SourceQuoteStoreDiagnosticCode(StrEnum):
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    FUTURE_INGESTION = "future_ingestion"
    CLOCK_SKEW_DETECTED = "clock_skew_detected"
    CLOCK_SKEW_EXCEEDED = "clock_skew_exceeded"
    STALE_EVICTED = "stale_evicted"
    INACTIVE_EVICTED = "inactive_evicted"


@dataclass(frozen=True, slots=True)
class SourceQuoteStoreDiagnostic:
    code: SourceQuoteStoreDiagnosticCode
    key: SourceQuoteKey
    detail: str


@dataclass(frozen=True, slots=True)
class SourceQuoteStoreApplyResult:
    accepted: tuple[SourceQuoteVersion, ...] = field(default_factory=tuple)
    diagnostics: tuple[SourceQuoteStoreDiagnostic, ...] = field(default_factory=tuple)
    added_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    rejected_count: int = 0


@dataclass(frozen=True, slots=True)
class SourceQuoteStoreEvictionResult:
    evicted: tuple[SourceQuoteVersion, ...]
    diagnostics: tuple[SourceQuoteStoreDiagnostic, ...]


class QuoteConsolidationDiagnosticCode(StrEnum):
    EQUIVALENT_SOURCE_OBSERVATIONS = "equivalent_source_observations"
    CONFLICTING_SOURCE_OBSERVATIONS = "conflicting_source_observations"


@dataclass(frozen=True, slots=True)
class QuoteConsolidationDiagnostic:
    code: QuoteConsolidationDiagnosticCode
    slot: PriceSlotKey
    transport_provider_ids: tuple[ProviderId, ...]
    detail: str


@dataclass(frozen=True, slots=True)
class QuoteConsolidationResult:
    quotes: tuple[OddsQuote, ...]
    selected_versions: tuple[SourceQuoteVersion, ...]
    diagnostics: tuple[QuoteConsolidationDiagnostic, ...]

    @property
    def conflict_count(self) -> int:
        return sum(
            1
            for item in self.diagnostics
            if item.code is QuoteConsolidationDiagnosticCode.CONFLICTING_SOURCE_OBSERVATIONS
        )

    @property
    def equivalent_overlap_count(self) -> int:
        return sum(
            1
            for item in self.diagnostics
            if item.code is QuoteConsolidationDiagnosticCode.EQUIVALENT_SOURCE_OBSERVATIONS
        )


class MultiSourceQuoteStore:
    """Keep transport observations separate, then consolidate by executable price origin."""

    def __init__(self, policy: RealtimeIngestionPolicy) -> None:
        if not isinstance(policy, RealtimeIngestionPolicy):
            raise ValueError("policy must be RealtimeIngestionPolicy")
        self._policy = policy
        self._current: dict[SourceQuoteKey, SourceQuoteVersion] = {}

    @property
    def policy(self) -> RealtimeIngestionPolicy:
        return self._policy

    def __len__(self) -> int:
        return len(self._current)

    @staticmethod
    def _fingerprint(quote: OddsQuote) -> tuple[object, ...]:
        effective_timestamp = quote.source_timestamp or quote.ingested_at
        return (
            _transport_provider_id(quote),
            quote.provider_id,
            quote.event_id,
            quote.market_id,
            quote.selection_id,
            quote.decimal_price,
            quote.status,
            quote.source_event_id,
            quote.source_market_id,
            quote.source_selection_id,
            effective_timestamp,
        )

    @staticmethod
    def _sort_key(
        quote: OddsQuote,
    ) -> tuple[str, str, str, str, str, datetime, datetime, str]:
        effective = quote.source_timestamp or quote.ingested_at
        return (
            quote.provider_id.value,
            _transport_provider_id(quote).value,
            quote.event_id.value,
            quote.market_id.value,
            quote.selection_id.value,
            effective,
            quote.ingested_at,
            quote.id.value,
        )

    @staticmethod
    def _diagnostic_sort_key(
        diagnostic: SourceQuoteStoreDiagnostic,
    ) -> tuple[str, str, str, str, str, str]:
        key = diagnostic.key
        return (
            key.provider_id.value,
            key.transport_provider_id.value,
            key.event_id.value,
            key.market_id.value,
            key.selection_id.value,
            diagnostic.code.value,
        )

    def apply(
        self,
        quotes: Iterable[OddsQuote],
        *,
        observed_at: datetime,
    ) -> SourceQuoteStoreApplyResult:
        observed = _aware_utc(observed_at, field_name="observed_at")
        quote_values = tuple(quotes)
        if any(not isinstance(quote, OddsQuote) for quote in quote_values):
            raise ValueError("quotes must contain OddsQuote values")

        accepted: list[SourceQuoteVersion] = []
        diagnostics: list[SourceQuoteStoreDiagnostic] = []
        added_count = 0
        updated_count = 0
        duplicate_count = 0
        rejected_count = 0

        for quote in sorted(quote_values, key=self._sort_key):
            key = SourceQuoteKey.from_quote(quote)
            effective = quote.source_timestamp or quote.ingested_at

            if quote.ingested_at > observed:
                diagnostics.append(
                    SourceQuoteStoreDiagnostic(
                        code=SourceQuoteStoreDiagnosticCode.FUTURE_INGESTION,
                        key=key,
                        detail="quote was ingested after the live-store observation time",
                    )
                )
                rejected_count += 1
                continue

            future_delta = effective - observed
            if future_delta > self._policy.clock_skew_tolerance:
                diagnostics.append(
                    SourceQuoteStoreDiagnostic(
                        code=SourceQuoteStoreDiagnosticCode.CLOCK_SKEW_EXCEEDED,
                        key=key,
                        detail=(
                            "quote effective timestamp exceeds observation time by more than "
                            "the configured clock-skew tolerance"
                        ),
                    )
                )
                rejected_count += 1
                continue
            if future_delta > timedelta(0):
                diagnostics.append(
                    SourceQuoteStoreDiagnostic(
                        code=SourceQuoteStoreDiagnosticCode.CLOCK_SKEW_DETECTED,
                        key=key,
                        detail=(
                            "quote effective timestamp is slightly ahead of the local clock; "
                            "stored but not eligible until local time catches up"
                        ),
                    )
                )

            current = self._current.get(key)
            if current is not None:
                current_effective = current.effective_timestamp
                backward_delta = current_effective - effective
                if backward_delta > self._policy.clock_skew_tolerance:
                    diagnostics.append(
                        SourceQuoteStoreDiagnostic(
                            code=SourceQuoteStoreDiagnosticCode.OUT_OF_ORDER,
                            key=key,
                            detail=(
                                "incoming quote effective timestamp is older than the current "
                                "source observation beyond the clock-skew tolerance"
                            ),
                        )
                    )
                    rejected_count += 1
                    continue

                if self._fingerprint(current.quote) == self._fingerprint(quote):
                    diagnostics.append(
                        SourceQuoteStoreDiagnostic(
                            code=SourceQuoteStoreDiagnosticCode.DUPLICATE,
                            key=key,
                            detail="incoming observation does not change source quote state",
                        )
                    )
                    duplicate_count += 1
                    continue

                if effective < current_effective and quote.ingested_at <= current.quote.ingested_at:
                    diagnostics.append(
                        SourceQuoteStoreDiagnostic(
                            code=SourceQuoteStoreDiagnosticCode.OUT_OF_ORDER,
                            key=key,
                            detail=(
                                "minor backward source-clock movement was not accompanied by a "
                                "newer ingestion timestamp"
                            ),
                        )
                    )
                    rejected_count += 1
                    continue

                revision = current.revision + 1
                updated_count += 1
            else:
                revision = 1
                added_count += 1

            version = SourceQuoteVersion(
                key=key,
                revision=revision,
                quote=quote,
                observed_at=observed,
            )
            self._current[key] = version
            accepted.append(version)

        return SourceQuoteStoreApplyResult(
            accepted=tuple(accepted),
            diagnostics=tuple(sorted(diagnostics, key=self._diagnostic_sort_key)),
            added_count=added_count,
            updated_count=updated_count,
            duplicate_count=duplicate_count,
            rejected_count=rejected_count,
        )

    def fresh_versions(self, *, as_of: datetime) -> tuple[SourceQuoteVersion, ...]:
        moment = _aware_utc(as_of, field_name="as_of")
        values: list[SourceQuoteVersion] = []
        for version in self._current.values():
            quote = version.quote
            effective = version.effective_timestamp
            if quote.status is not QuoteStatus.ACTIVE:
                continue
            if quote.ingested_at > moment or effective > moment:
                continue
            if moment - effective > self._policy.freshness_window:
                continue
            values.append(version)
        return tuple(
            sorted(
                values,
                key=lambda item: (
                    item.key.event_id.value,
                    item.key.market_id.value,
                    item.key.selection_id.value,
                    item.key.provider_id.value,
                    item.key.transport_provider_id.value,
                ),
            )
        )

    def consolidate_fresh(
        self,
        *,
        as_of: datetime,
        excluded_keys: Iterable[SourceQuoteKey] = (),
    ) -> QuoteConsolidationResult:
        """Collapse source observations into one deterministic quote per bookmaker slot."""
        excluded = frozenset(excluded_keys)
        grouped: dict[PriceSlotKey, list[SourceQuoteVersion]] = defaultdict(list)
        for version in self.fresh_versions(as_of=as_of):
            if version.key in excluded:
                continue
            grouped[PriceSlotKey.from_quote(version.quote)].append(version)

        selected: list[SourceQuoteVersion] = []
        diagnostics: list[QuoteConsolidationDiagnostic] = []
        for slot in sorted(grouped):
            versions = grouped[slot]
            newest_timestamp = max(version.effective_timestamp for version in versions)
            newest = [
                version for version in versions if version.effective_timestamp == newest_timestamp
            ]
            newest.sort(
                key=lambda item: (item.key.transport_provider_id.value, item.quote.id.value)
            )

            semantics = {(item.quote.decimal_price, item.quote.status) for item in newest}
            transports = tuple(sorted({item.key.transport_provider_id for item in newest}))
            if len(semantics) > 1:
                diagnostics.append(
                    QuoteConsolidationDiagnostic(
                        code=QuoteConsolidationDiagnosticCode.CONFLICTING_SOURCE_OBSERVATIONS,
                        slot=slot,
                        transport_provider_ids=transports,
                        detail=(
                            "equal-time source observations conflict for the same executable "
                            "price-provider slot; slot excluded fail-closed"
                        ),
                    )
                )
                continue

            selected.append(newest[0])
            if len(newest) > 1:
                diagnostics.append(
                    QuoteConsolidationDiagnostic(
                        code=QuoteConsolidationDiagnosticCode.EQUIVALENT_SOURCE_OBSERVATIONS,
                        slot=slot,
                        transport_provider_ids=transports,
                        detail=(
                            "equivalent equal-time observations consolidated deterministically "
                            "while retaining every source observation in live state"
                        ),
                    )
                )

        selected.sort(
            key=lambda item: (
                item.key.event_id.value,
                item.key.market_id.value,
                item.key.selection_id.value,
                item.key.provider_id.value,
                item.key.transport_provider_id.value,
            )
        )
        diagnostics.sort(
            key=lambda item: (
                item.slot.event_id.value,
                item.slot.market_id.value,
                item.slot.selection_id.value,
                item.slot.provider_id.value,
                item.code.value,
            )
        )
        return QuoteConsolidationResult(
            quotes=tuple(item.quote for item in selected),
            selected_versions=tuple(selected),
            diagnostics=tuple(diagnostics),
        )

    def fresh_quotes(
        self,
        *,
        as_of: datetime,
        excluded_keys: Iterable[SourceQuoteKey] = (),
    ) -> tuple[OddsQuote, ...]:
        return self.consolidate_fresh(as_of=as_of, excluded_keys=excluded_keys).quotes

    def stale_count(self, *, as_of: datetime) -> int:
        moment = _aware_utc(as_of, field_name="as_of")
        return sum(
            1
            for version in self._current.values()
            if version.effective_timestamp <= moment
            and moment - version.effective_timestamp > self._policy.freshness_window
        )

    def maximum_quote_age(self, *, as_of: datetime) -> timedelta | None:
        moment = _aware_utc(as_of, field_name="as_of")
        fresh = self.consolidate_fresh(as_of=moment).selected_versions
        if not fresh:
            return None
        return max(moment - version.effective_timestamp for version in fresh)

    def evict_stale(self, *, as_of: datetime) -> SourceQuoteStoreEvictionResult:
        moment = _aware_utc(as_of, field_name="as_of")
        evicted: list[SourceQuoteVersion] = []
        diagnostics: list[SourceQuoteStoreDiagnostic] = []
        for key, version in tuple(self._current.items()):
            effective = version.effective_timestamp
            code: SourceQuoteStoreDiagnosticCode | None = None
            detail = ""
            if version.quote.status is not QuoteStatus.ACTIVE:
                code = SourceQuoteStoreDiagnosticCode.INACTIVE_EVICTED
                detail = "inactive source observation removed from live state"
            elif effective <= moment and moment - effective > self._policy.freshness_window:
                code = SourceQuoteStoreDiagnosticCode.STALE_EVICTED
                detail = "source observation exceeded the configured freshness window"
            if code is None:
                continue
            del self._current[key]
            evicted.append(version)
            diagnostics.append(SourceQuoteStoreDiagnostic(code=code, key=key, detail=detail))

        evicted.sort(
            key=lambda item: (
                item.key.event_id.value,
                item.key.market_id.value,
                item.key.selection_id.value,
                item.key.provider_id.value,
                item.key.transport_provider_id.value,
            )
        )
        diagnostics.sort(key=self._diagnostic_sort_key)
        return SourceQuoteStoreEvictionResult(
            evicted=tuple(evicted),
            diagnostics=tuple(diagnostics),
        )
