"""Provider-neutral source records and capability metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from arbiscan.domain import (
    CompetitionId,
    EventId,
    MarketId,
    Provider,
    ProviderId,
    SelectionId,
    Sport,
)
from arbiscan.providers.errors import ProviderContractError


class ProviderCapability(StrEnum):
    """Capabilities that an adapter can explicitly declare."""

    SPORT_DISCOVERY = "sport_discovery"
    COMPETITION_DISCOVERY = "competition_discovery"
    EVENT_DISCOVERY = "event_discovery"
    ODDS_SNAPSHOTS = "odds_snapshots"
    ODDS_STREAMING = "odds_streaming"
    HEALTH = "health"
    RATE_LIMIT_METADATA = "rate_limit_metadata"
    CANONICAL_ID_HINTS = "canonical_id_hints"


class ProviderOperation(StrEnum):
    """Stable operation names used by errors, retries, and observability."""

    SUPPORTED_SPORTS = "supported_sports"
    DISCOVER_COMPETITIONS = "discover_competitions"
    DISCOVER_EVENTS = "discover_events"
    FETCH_ODDS = "fetch_odds"
    STREAM_ODDS = "stream_odds"
    HEALTH = "health"
    RATE_LIMIT = "rate_limit"


class ProviderHealthState(StrEnum):
    """Coarse provider availability state."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class SourceOddsFormat(StrEnum):
    """Odds encodings a provider source record may retain before normalization."""

    DECIMAL = "decimal"
    FRACTIONAL = "fractional"
    AMERICAN = "american"
    IMPLIED_PROBABILITY = "implied_probability"


def _text(value: object, *, field_name: str, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise ProviderContractError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ProviderContractError(f"{field_name} must not be empty")
    if len(normalized) > max_length:
        raise ProviderContractError(f"{field_name} exceeds maximum length {max_length}")
    if any(ord(char) < 32 and char not in "\t" for char in normalized):
        raise ProviderContractError(f"{field_name} contains control characters")
    return normalized


def _optional_text(value: object | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name=field_name)


def _aware_utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ProviderContractError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProviderContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _optional_aware_utc(value: object | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _aware_utc(value, field_name=field_name)


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Immutable capability declaration for one adapter."""

    values: frozenset[ProviderCapability] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        values = frozenset(self.values)
        if any(not isinstance(value, ProviderCapability) for value in values):
            raise ProviderContractError("provider capabilities contain an invalid value")
        object.__setattr__(self, "values", values)

    def supports(self, capability: ProviderCapability) -> bool:
        """Return whether the capability is explicitly declared."""
        if not isinstance(capability, ProviderCapability):
            raise ProviderContractError("capability must be ProviderCapability")
        return capability in self.values


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """Health result returned by the provider boundary."""

    provider_id: ProviderId
    state: ProviderHealthState
    checked_at: datetime
    detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise ProviderContractError("provider health provider_id must be ProviderId")
        if not isinstance(self.state, ProviderHealthState):
            raise ProviderContractError("provider health state must be ProviderHealthState")
        object.__setattr__(
            self,
            "checked_at",
            _aware_utc(self.checked_at, field_name="provider_health.checked_at"),
        )
        object.__setattr__(
            self,
            "detail",
            _optional_text(self.detail, field_name="provider_health.detail"),
        )


@dataclass(frozen=True, slots=True)
class RateLimitSnapshot:
    """Provider rate-limit metadata captured at one point in time."""

    provider_id: ProviderId
    observed_at: datetime
    limit: int | None = None
    remaining: int | None = None
    resets_at: datetime | None = None
    retry_after: timedelta | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise ProviderContractError("rate limit provider_id must be ProviderId")
        object.__setattr__(
            self,
            "observed_at",
            _aware_utc(self.observed_at, field_name="rate_limit.observed_at"),
        )
        object.__setattr__(
            self,
            "resets_at",
            _optional_aware_utc(self.resets_at, field_name="rate_limit.resets_at"),
        )
        if self.limit is not None and (type(self.limit) is not int or self.limit < 0):
            raise ProviderContractError("rate limit limit must be a non-negative integer")
        if self.remaining is not None:
            if type(self.remaining) is not int or self.remaining < 0:
                raise ProviderContractError("rate limit remaining must be non-negative integer")
            if self.limit is None:
                raise ProviderContractError("rate limit remaining requires limit")
            if self.remaining > self.limit:
                raise ProviderContractError("rate limit remaining cannot exceed limit")
        if self.retry_after is not None:
            if not isinstance(self.retry_after, timedelta):
                raise ProviderContractError("rate limit retry_after must be timedelta")
            if self.retry_after.total_seconds() < 0:
                raise ProviderContractError("rate limit retry_after cannot be negative")


@dataclass(frozen=True, slots=True)
class SourceCompetition:
    """Validated provider-neutral representation of a provider competition record."""

    external_id: str
    sport: Sport
    name: str
    region: str | None = None
    season: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_id",
            _text(self.external_id, field_name="source_competition.external_id"),
        )
        if not isinstance(self.sport, Sport):
            raise ProviderContractError("source competition sport must be Sport")
        object.__setattr__(
            self,
            "name",
            _text(self.name, field_name="source_competition.name"),
        )
        object.__setattr__(
            self,
            "region",
            _optional_text(self.region, field_name="source_competition.region"),
        )
        object.__setattr__(
            self,
            "season",
            _optional_text(self.season, field_name="source_competition.season"),
        )


@dataclass(frozen=True, slots=True)
class SourceParticipant:
    """Provider participant identity before canonical participant resolution."""

    external_id: str
    name: str
    role: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_id",
            _text(self.external_id, field_name="source_participant.external_id"),
        )
        object.__setattr__(
            self,
            "name",
            _text(self.name, field_name="source_participant.name"),
        )
        object.__setattr__(
            self,
            "role",
            _optional_text(self.role, field_name="source_participant.role"),
        )


@dataclass(frozen=True, slots=True)
class SourceEvent:
    """Provider event record before cross-provider identity resolution."""

    external_id: str
    sport: Sport
    competition_external_id: str
    participants: tuple[SourceParticipant, ...]
    scheduled_start: datetime
    source_status: str = "unknown"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_id",
            _text(self.external_id, field_name="source_event.external_id"),
        )
        if not isinstance(self.sport, Sport):
            raise ProviderContractError("source event sport must be Sport")
        object.__setattr__(
            self,
            "competition_external_id",
            _text(
                self.competition_external_id,
                field_name="source_event.competition_external_id",
            ),
        )
        participants = tuple(self.participants)
        if not participants:
            raise ProviderContractError("source event requires at least one participant")
        if any(not isinstance(participant, SourceParticipant) for participant in participants):
            raise ProviderContractError(
                "source event participants must be SourceParticipant values"
            )
        participant_ids = [participant.external_id for participant in participants]
        if len(set(participant_ids)) != len(participant_ids):
            raise ProviderContractError("source event participant IDs must be unique")
        object.__setattr__(self, "participants", participants)
        object.__setattr__(
            self,
            "scheduled_start",
            _aware_utc(self.scheduled_start, field_name="source_event.scheduled_start"),
        )
        object.__setattr__(
            self,
            "source_status",
            _text(self.source_status, field_name="source_event.source_status"),
        )


@dataclass(frozen=True, slots=True)
class SourceSelectionQuote:
    """Provider selection and price before market/odds normalization."""

    external_selection_id: str
    label: str
    price: str
    odds_format: SourceOddsFormat
    source_status: str = "active"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_selection_id",
            _text(
                self.external_selection_id,
                field_name="source_selection_quote.external_selection_id",
            ),
        )
        object.__setattr__(
            self,
            "label",
            _text(self.label, field_name="source_selection_quote.label"),
        )
        object.__setattr__(
            self,
            "price",
            _text(self.price, field_name="source_selection_quote.price", max_length=128),
        )
        if not isinstance(self.odds_format, SourceOddsFormat):
            raise ProviderContractError("source selection odds_format must be SourceOddsFormat")
        object.__setattr__(
            self,
            "source_status",
            _text(self.source_status, field_name="source_selection_quote.source_status"),
        )


@dataclass(frozen=True, slots=True)
class SourceMarket:
    """Provider market record before canonical market normalization.

    ``price_provider`` is set by aggregator adapters when the transport/source
    provider differs from the bookmaker or exchange actually offering the price.
    ``source_timestamp`` preserves the most specific update timestamp supplied by
    the upstream feed, allowing freshness to be evaluated per bookmaker market.
    """

    external_event_id: str
    external_market_id: str
    label: str
    selections: tuple[SourceSelectionQuote, ...]
    source_status: str = "active"
    price_provider: Provider | None = None
    source_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_event_id",
            _text(self.external_event_id, field_name="source_market.external_event_id"),
        )
        object.__setattr__(
            self,
            "external_market_id",
            _text(self.external_market_id, field_name="source_market.external_market_id"),
        )
        object.__setattr__(
            self,
            "label",
            _text(self.label, field_name="source_market.label"),
        )
        selections = tuple(self.selections)
        if not selections:
            raise ProviderContractError("source market requires at least one selection")
        if any(not isinstance(selection, SourceSelectionQuote) for selection in selections):
            raise ProviderContractError(
                "source market selections must be SourceSelectionQuote values"
            )
        selection_ids = [selection.external_selection_id for selection in selections]
        if len(set(selection_ids)) != len(selection_ids):
            raise ProviderContractError("source market selection IDs must be unique")
        object.__setattr__(self, "selections", selections)
        object.__setattr__(
            self,
            "source_status",
            _text(self.source_status, field_name="source_market.source_status"),
        )
        if self.price_provider is not None and not isinstance(self.price_provider, Provider):
            raise ProviderContractError("source market price_provider must be Provider")
        object.__setattr__(
            self,
            "source_timestamp",
            _optional_aware_utc(
                self.source_timestamp,
                field_name="source_market.source_timestamp",
            ),
        )


@dataclass(frozen=True, slots=True)
class OddsSnapshot:
    """One immutable odds payload after adapter-level structural validation."""

    provider_id: ProviderId
    external_event_id: str
    markets: tuple[SourceMarket, ...]
    ingested_at: datetime
    source_timestamp: datetime | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise ProviderContractError("odds snapshot provider_id must be ProviderId")
        object.__setattr__(
            self,
            "external_event_id",
            _text(self.external_event_id, field_name="odds_snapshot.external_event_id"),
        )
        markets = tuple(self.markets)
        if any(not isinstance(market, SourceMarket) for market in markets):
            raise ProviderContractError("odds snapshot markets must be SourceMarket values")
        if any(market.external_event_id != self.external_event_id for market in markets):
            raise ProviderContractError("every snapshot market must reference the snapshot event")
        market_ids = [market.external_market_id for market in markets]
        if len(set(market_ids)) != len(market_ids):
            raise ProviderContractError("odds snapshot market IDs must be unique")
        object.__setattr__(self, "markets", markets)
        object.__setattr__(
            self,
            "ingested_at",
            _aware_utc(self.ingested_at, field_name="odds_snapshot.ingested_at"),
        )
        object.__setattr__(
            self,
            "source_timestamp",
            _optional_aware_utc(
                self.source_timestamp,
                field_name="odds_snapshot.source_timestamp",
            ),
        )
        object.__setattr__(
            self,
            "trace_id",
            _optional_text(self.trace_id, field_name="odds_snapshot.trace_id"),
        )


class CanonicalIdHooks(Protocol):
    """Optional normalization hooks that map source records to known canonical IDs."""

    def competition_id(self, record: SourceCompetition) -> CompetitionId | None: ...

    def event_id(self, record: SourceEvent) -> EventId | None: ...

    def market_id(self, record: SourceMarket) -> MarketId | None: ...

    def selection_id(
        self,
        market: SourceMarket,
        record: SourceSelectionQuote,
    ) -> SelectionId | None: ...
