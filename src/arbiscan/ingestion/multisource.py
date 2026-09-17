"""Phase-16 multi-source quote observation identity and consolidation.

This module keeps transport/source identity separate from executable price-origin
identity. It intentionally has no source-preference ranking: when independent
transports report the same bookmaker outcome, the newest trustworthy observation
wins; materially conflicting observations at the same effective timestamp fail
closed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from arbiscan.domain import EventId, MarketId, OddsQuote, ProviderId, SelectionId


@dataclass(frozen=True, slots=True, order=True)
class SourceObservationKey:
    """Identity of one transport-specific observation stream."""

    transport_provider_id: ProviderId
    provider_id: ProviderId
    event_id: EventId
    market_id: MarketId
    selection_id: SelectionId

    @classmethod
    def from_quote(cls, quote: OddsQuote) -> SourceObservationKey:
        return cls(
            transport_provider_id=quote.transport_provider_id or quote.provider_id,
            provider_id=quote.provider_id,
            event_id=quote.event_id,
            market_id=quote.market_id,
            selection_id=quote.selection_id,
        )


@dataclass(frozen=True, slots=True, order=True)
class PriceSlotKey:
    """Executable price slot; transport identity is deliberately excluded."""

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


class ConsolidationDiagnosticCode(StrEnum):
    """Stable reasons emitted while consolidating overlapping observations."""

    EQUIVALENT_OVERLAP = "equivalent_overlap"
    MATERIAL_CONFLICT = "material_conflict"


@dataclass(frozen=True, slots=True)
class ConsolidationDiagnostic:
    code: ConsolidationDiagnosticCode
    slot: PriceSlotKey
    effective_timestamp: datetime
    transport_provider_ids: tuple[ProviderId, ...]
    quote_ids: tuple[str, ...]
    detail: str


@dataclass(frozen=True, slots=True)
class ConsolidationResult:
    """Executable quotes plus overlap evidence and fail-closed diagnostics."""

    quotes: tuple[OddsQuote, ...]
    diagnostics: tuple[ConsolidationDiagnostic, ...] = field(default_factory=tuple)
    equivalent_overlap_count: int = 0
    conflict_count: int = 0


def effective_timestamp(quote: OddsQuote) -> datetime:
    """Return the existing canonical freshness timestamp for one observation."""
    return quote.source_timestamp or quote.ingested_at


def _observation_sort_key(quote: OddsQuote) -> tuple[str, datetime, datetime, str]:
    transport = quote.transport_provider_id or quote.provider_id
    return (
        transport.value,
        effective_timestamp(quote),
        quote.ingested_at,
        quote.id.value,
    )


def _output_sort_key(quote: OddsQuote) -> tuple[str, str, str, str, str]:
    transport = quote.transport_provider_id or quote.provider_id
    return (
        quote.event_id.value,
        quote.market_id.value,
        quote.selection_id.value,
        quote.provider_id.value,
        transport.value,
    )


def consolidate_quotes(quotes: Iterable[OddsQuote]) -> ConsolidationResult:
    """Collapse transport overlap to one executable quote per price-origin slot.

    The caller is responsible for applying freshness/status eligibility before this
    function. For every bookmaker/event/market/selection slot:

    * only observations with the newest effective timestamp are considered;
    * equivalent same-time price/status observations select one deterministically;
    * materially conflicting same-time observations emit a diagnostic and no quote.

    All input quote objects remain available to the caller for audit persistence;
    consolidation only decides which observation may enter executable market books.
    """
    quote_values = tuple(quotes)
    if any(not isinstance(quote, OddsQuote) for quote in quote_values):
        raise ValueError("quotes must contain OddsQuote values")

    grouped: dict[PriceSlotKey, list[OddsQuote]] = defaultdict(list)
    for quote in quote_values:
        grouped[PriceSlotKey.from_quote(quote)].append(quote)

    selected: list[OddsQuote] = []
    diagnostics: list[ConsolidationDiagnostic] = []
    equivalent_overlap_count = 0
    conflict_count = 0

    for slot in sorted(grouped):
        observations = grouped[slot]
        newest_timestamp = max(effective_timestamp(quote) for quote in observations)
        newest = [quote for quote in observations if effective_timestamp(quote) == newest_timestamp]
        newest.sort(key=_observation_sort_key)

        semantic_states = {(quote.decimal_price, quote.status) for quote in newest}
        transports = tuple(
            sorted(
                {quote.transport_provider_id or quote.provider_id for quote in newest},
                key=lambda provider_id: provider_id.value,
            )
        )
        quote_ids = tuple(quote.id.value for quote in newest)

        if len(semantic_states) > 1:
            conflict_count += 1
            diagnostics.append(
                ConsolidationDiagnostic(
                    code=ConsolidationDiagnosticCode.MATERIAL_CONFLICT,
                    slot=slot,
                    effective_timestamp=newest_timestamp,
                    transport_provider_ids=transports,
                    quote_ids=quote_ids,
                    detail=(
                        "equal-time transport observations disagree on material "
                        "price/status state; executable slot suppressed"
                    ),
                )
            )
            continue

        chosen = newest[0]
        selected.append(chosen)
        if len(newest) > 1:
            equivalent_overlap_count += 1
            diagnostics.append(
                ConsolidationDiagnostic(
                    code=ConsolidationDiagnosticCode.EQUIVALENT_OVERLAP,
                    slot=slot,
                    effective_timestamp=newest_timestamp,
                    transport_provider_ids=transports,
                    quote_ids=quote_ids,
                    detail=(
                        "equivalent equal-time observations consolidated to one "
                        "deterministically selected executable quote"
                    ),
                )
            )

    return ConsolidationResult(
        quotes=tuple(sorted(selected, key=_output_sort_key)),
        diagnostics=tuple(
            sorted(
                diagnostics,
                key=lambda item: (
                    item.slot.event_id.value,
                    item.slot.market_id.value,
                    item.slot.selection_id.value,
                    item.slot.provider_id.value,
                    item.effective_timestamp,
                    item.code.value,
                ),
            )
        ),
        equivalent_overlap_count=equivalent_overlap_count,
        conflict_count=conflict_count,
    )
