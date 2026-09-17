"""Strict mapped source-to-canonical conversion with fail-closed diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256

from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    Provider,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
)
from arbiscan.matching.catalog import CanonicalRegistry
from arbiscan.matching.hooks import MatchedCanonicalIdHooks
from arbiscan.normalization.odds import OddsNormalizationError, normalize_odds
from arbiscan.providers.models import (
    CanonicalIdHooks,
    OddsSnapshot,
    SourceEvent,
    SourceMarket,
    SourceSelectionQuote,
)


class NormalizationIssueCode(StrEnum):
    """Stable fail-closed reasons emitted by strict mapped normalization."""

    MISSING_IDENTITY_HOOKS = "missing_identity_hooks"
    UNMAPPED_EVENT = "unmapped_event"
    IDENTITY_MISMATCH = "identity_mismatch"
    UNMAPPED_MARKET = "unmapped_market"
    MARKET_EVENT_MISMATCH = "market_event_mismatch"
    UNMAPPED_SELECTION = "unmapped_selection"
    SELECTION_MARKET_MISMATCH = "selection_market_mismatch"
    STALE_SNAPSHOT = "stale_snapshot"
    FUTURE_SNAPSHOT = "future_snapshot"
    FUTURE_INGESTION = "future_ingestion"
    INACTIVE_MARKET = "inactive_market"
    INACTIVE_SELECTION = "inactive_selection"
    UNSUPPORTED_ODDS_FORMAT = "unsupported_odds_format"
    MALFORMED_PRICE = "malformed_price"


@dataclass(frozen=True, slots=True)
class NormalizationIssue:
    """Traceable reason why source data was not eligible for the canonical book."""

    code: NormalizationIssueCode
    provider_id: ProviderId
    external_event_id: str
    detail: str
    external_market_id: str | None = None
    external_selection_id: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """Canonical quotes plus all rejected-source diagnostics for one snapshot."""

    quotes: tuple[OddsQuote, ...]
    issues: tuple[NormalizationIssue, ...]


def _utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _status(value: str) -> QuoteStatus:
    normalized = value.strip().casefold()
    if normalized == "active":
        return QuoteStatus.ACTIVE
    if normalized == "suspended":
        return QuoteStatus.SUSPENDED
    if normalized == "closed":
        return QuoteStatus.CLOSED
    return QuoteStatus.UNKNOWN


def _issue(
    code: NormalizationIssueCode,
    provider: Provider,
    event: SourceEvent,
    detail: str,
    *,
    market: SourceMarket | None = None,
    selection: SourceSelectionQuote | None = None,
) -> NormalizationIssue:
    return NormalizationIssue(
        code=code,
        provider_id=provider.id,
        external_event_id=event.external_id,
        external_market_id=None if market is None else market.external_market_id,
        external_selection_id=None if selection is None else selection.external_selection_id,
        detail=detail,
    )


def _quote_id(
    *,
    source_provider_id: ProviderId,
    price_provider_id: ProviderId,
    event_id: EventId,
    market_id: MarketId,
    selection_id: SelectionId,
    source_event_id: str,
    source_market_id: str,
    source_selection_id: str,
    effective_timestamp: datetime,
) -> QuoteId:
    """Build a bounded collision-resistant ID for one transport observation."""
    identity = "\x1f".join(
        (
            source_provider_id.value,
            price_provider_id.value,
            event_id.value,
            market_id.value,
            selection_id.value,
            source_event_id,
            source_market_id,
            source_selection_id,
            effective_timestamp.isoformat(),
        )
    )
    return QuoteId(f"quote:{sha256(identity.encode('utf-8')).hexdigest()}")


def _market_timestamp(
    market: SourceMarket,
    snapshot: OddsSnapshot,
) -> tuple[datetime, datetime | None]:
    source_timestamp = market.source_timestamp or snapshot.source_timestamp
    return source_timestamp or snapshot.ingested_at, source_timestamp


def normalize_source_snapshot(
    *,
    provider: Provider,
    hooks: CanonicalIdHooks | None,
    event: SourceEvent,
    snapshot: OddsSnapshot,
    registry: CanonicalRegistry,
    as_of: datetime,
    freshness_window: timedelta,
) -> NormalizationResult:
    """Normalize one validated source snapshot using explicit canonical mappings only.

    This bridge deliberately performs no fuzzy event/market/selection identity matching.
    Source odds are converted through the Phase 7 exact odds normalizer before an
    ``OddsQuote`` is created. Aggregators may identify the underlying bookmaker on
    each ``SourceMarket``; when present, that bookmaker remains the canonical price
    provider while ``provider`` is preserved separately as the source/transport
    provider on every quote observation.

    Static/legacy identity hooks still require an exact source/canonical scheduled
    start. A ``MatchedCanonicalIdHooks`` wrapper may carry a Phase-8 ``MATCHED``
    decision; only that verified decision is permitted to relax the exact timestamp
    equality after the matcher has already enforced its configured tolerance.
    """
    now = _utc(as_of, field_name="as_of")
    if not isinstance(freshness_window, timedelta) or freshness_window <= timedelta(0):
        raise ValueError("freshness_window must be a positive timedelta")
    if snapshot.provider_id != provider.id:
        raise ValueError("snapshot provider_id must match the transport provider")

    issues: list[NormalizationIssue] = []
    quotes: list[OddsQuote] = []

    if hooks is None:
        return NormalizationResult(
            quotes=(),
            issues=(
                _issue(
                    NormalizationIssueCode.MISSING_IDENTITY_HOOKS,
                    provider,
                    event,
                    "provider does not expose explicit canonical identity mappings",
                ),
            ),
        )

    event_id = hooks.event_id(event)
    canonical_event = None if event_id is None else registry.event(event_id)
    if event_id is None or canonical_event is None:
        return NormalizationResult(
            quotes=(),
            issues=(
                _issue(
                    NormalizationIssueCode.UNMAPPED_EVENT,
                    provider,
                    event,
                    "source event has no known canonical identity",
                ),
            ),
        )

    verified_phase8_match = isinstance(
        hooks, MatchedCanonicalIdHooks
    ) and hooks.has_verified_event_match(event, event_id)
    if canonical_event.sport is not event.sport or (
        canonical_event.scheduled_start != event.scheduled_start and not verified_phase8_match
    ):
        return NormalizationResult(
            quotes=(),
            issues=(
                _issue(
                    NormalizationIssueCode.IDENTITY_MISMATCH,
                    provider,
                    event,
                    "explicit event mapping conflicts with canonical sport or unverified start time",
                ),
            ),
        )

    if snapshot.ingested_at > now:
        return NormalizationResult(
            quotes=(),
            issues=(
                _issue(
                    NormalizationIssueCode.FUTURE_INGESTION,
                    provider,
                    event,
                    "snapshot was ingested after the evaluation time",
                ),
            ),
        )

    for market in snapshot.markets:
        effective_timestamp, quote_source_timestamp = _market_timestamp(market, snapshot)
        age = now - effective_timestamp
        if age < timedelta(0):
            issues.append(
                _issue(
                    NormalizationIssueCode.FUTURE_SNAPSHOT,
                    provider,
                    event,
                    "market source timestamp lies in the future",
                    market=market,
                )
            )
            continue
        if age > freshness_window:
            issues.append(
                _issue(
                    NormalizationIssueCode.STALE_SNAPSHOT,
                    provider,
                    event,
                    "market exceeds the configured freshness window",
                    market=market,
                )
            )
            continue

        market_id = hooks.market_id(market)
        canonical_market = None if market_id is None else registry.market(market_id)
        if market_id is None or canonical_market is None:
            issues.append(
                _issue(
                    NormalizationIssueCode.UNMAPPED_MARKET,
                    provider,
                    event,
                    "source market has no known canonical identity",
                    market=market,
                )
            )
            continue
        if canonical_market.event_id != event_id:
            issues.append(
                _issue(
                    NormalizationIssueCode.MARKET_EVENT_MISMATCH,
                    provider,
                    event,
                    "canonical market belongs to a different event",
                    market=market,
                )
            )
            continue
        if _status(market.source_status) is not QuoteStatus.ACTIVE:
            issues.append(
                _issue(
                    NormalizationIssueCode.INACTIVE_MARKET,
                    provider,
                    event,
                    "source market is not active",
                    market=market,
                )
            )
            continue

        quote_provider = market.price_provider or provider
        for selection in market.selections:
            selection_id = hooks.selection_id(market, selection)
            canonical_selection = None if selection_id is None else registry.selection(selection_id)
            if selection_id is None or canonical_selection is None:
                issues.append(
                    _issue(
                        NormalizationIssueCode.UNMAPPED_SELECTION,
                        provider,
                        event,
                        "source selection has no known canonical identity",
                        market=market,
                        selection=selection,
                    )
                )
                continue
            if canonical_selection.market_id != market_id:
                issues.append(
                    _issue(
                        NormalizationIssueCode.SELECTION_MARKET_MISMATCH,
                        provider,
                        event,
                        "canonical selection belongs to a different market",
                        market=market,
                        selection=selection,
                    )
                )
                continue
            if _status(selection.source_status) is not QuoteStatus.ACTIVE:
                issues.append(
                    _issue(
                        NormalizationIssueCode.INACTIVE_SELECTION,
                        provider,
                        event,
                        "source selection is not active",
                        market=market,
                        selection=selection,
                    )
                )
                continue

            try:
                price = normalize_odds(selection.price, selection.odds_format)
            except OddsNormalizationError as exc:
                issues.append(
                    _issue(
                        NormalizationIssueCode.MALFORMED_PRICE,
                        provider,
                        event,
                        str(exc),
                        market=market,
                        selection=selection,
                    )
                )
                continue

            quotes.append(
                OddsQuote(
                    id=_quote_id(
                        source_provider_id=provider.id,
                        price_provider_id=quote_provider.id,
                        event_id=event_id,
                        market_id=market_id,
                        selection_id=selection_id,
                        source_event_id=event.external_id,
                        source_market_id=market.external_market_id,
                        source_selection_id=selection.external_selection_id,
                        effective_timestamp=effective_timestamp,
                    ),
                    provider_id=quote_provider.id,
                    source_provider_id=provider.id,
                    event_id=event_id,
                    market_id=market_id,
                    selection_id=selection_id,
                    decimal_price=price,
                    source_event_id=event.external_id,
                    source_market_id=market.external_market_id,
                    source_selection_id=selection.external_selection_id,
                    source_timestamp=quote_source_timestamp,
                    ingested_at=snapshot.ingested_at,
                    status=QuoteStatus.ACTIVE,
                    trace_id=snapshot.trace_id,
                    raw_source_reference=(
                        f"source://{provider.id.value}/{quote_provider.id.value}/"
                        f"{event.external_id}/{market.external_market_id}/"
                        f"{selection.external_selection_id}"
                    ),
                )
            )

    return NormalizationResult(
        quotes=tuple(
            sorted(
                quotes,
                key=lambda quote: (
                    quote.market_id.value,
                    quote.selection_id.value,
                    quote.provider_id.value,
                    (quote.source_provider_id or quote.provider_id).value,
                ),
            )
        ),
        issues=tuple(
            sorted(
                issues,
                key=lambda item: (
                    item.code.value,
                    item.external_market_id or "",
                    item.external_selection_id or "",
                ),
            )
        ),
    )
