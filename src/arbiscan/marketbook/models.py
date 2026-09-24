"""Immutable provider-independent models for canonical best-price books."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from arbiscan.domain import (
    Event,
    EventId,
    Market,
    MarketId,
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    Selection,
    SelectionId,
)
from arbiscan.domain.validation import normalize_datetime


class MarketBookDiagnosticCode(StrEnum):
    """Stable fail-closed reasons emitted while constructing canonical market books."""

    DUPLICATE_QUOTE_ID = "duplicate_quote_id"
    UNKNOWN_EVENT = "unknown_event"
    UNKNOWN_MARKET = "unknown_market"
    UNKNOWN_SELECTION = "unknown_selection"
    QUOTE_EVENT_MISMATCH = "quote_event_mismatch"
    QUOTE_SELECTION_MISMATCH = "quote_selection_mismatch"
    PROVIDER_FILTERED = "provider_filtered"
    INACTIVE_QUOTE = "inactive_quote"
    FUTURE_INGESTION = "future_ingestion"
    FUTURE_QUOTE = "future_quote"
    STALE_QUOTE = "stale_quote"
    EVENT_NOT_PREMATCH = "event_not_prematch"
    INSUFFICIENT_OUTCOMES = "insufficient_outcomes"
    INCOMPLETE_MARKET = "incomplete_market"


@dataclass(frozen=True, slots=True)
class ProviderBookPolicy:
    """Explicit provider allow/deny policy applied before best-price selection."""

    included_provider_ids: tuple[ProviderId, ...] | None = None
    excluded_provider_ids: tuple[ProviderId, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        included = None if self.included_provider_ids is None else tuple(self.included_provider_ids)
        excluded = tuple(self.excluded_provider_ids)

        for label, values in (("included", included), ("excluded", excluded)):
            if values is None:
                continue
            if any(not isinstance(value, ProviderId) for value in values):
                raise ValueError(f"{label} provider IDs must contain ProviderId values")
            if len(set(values)) != len(values):
                raise ValueError(f"{label} provider IDs must be unique")

        included_set = set() if included is None else set(included)
        excluded_set = set(excluded)
        overlap = included_set & excluded_set
        if overlap:
            raise ValueError("provider IDs cannot be both included and excluded")

        if included is not None:
            included = tuple(sorted(included, key=lambda value: value.value))
        excluded = tuple(sorted(excluded, key=lambda value: value.value))
        object.__setattr__(self, "included_provider_ids", included)
        object.__setattr__(self, "excluded_provider_ids", excluded)

    def allows(self, provider_id: ProviderId) -> bool:
        """Return whether a provider is eligible under this policy."""
        if not isinstance(provider_id, ProviderId):
            raise ValueError("provider_id must be ProviderId")
        if provider_id in self.excluded_provider_ids:
            return False
        included = self.included_provider_ids
        return included is None or provider_id in included


@dataclass(frozen=True, slots=True)
class MarketBookDiagnostic:
    """Traceable reason a quote or market was excluded from a canonical book."""

    code: MarketBookDiagnosticCode
    detail: str
    event_id: EventId | None = None
    market_id: MarketId | None = None
    selection_id: SelectionId | None = None
    provider_id: ProviderId | None = None
    quote_id: QuoteId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, MarketBookDiagnosticCode):
            raise ValueError("diagnostic code must be MarketBookDiagnosticCode")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("diagnostic detail must be non-empty text")
        for value, expected_type, field_name in (
            (self.event_id, EventId, "event_id"),
            (self.market_id, MarketId, "market_id"),
            (self.selection_id, SelectionId, "selection_id"),
            (self.provider_id, ProviderId, "provider_id"),
            (self.quote_id, QuoteId, "quote_id"),
        ):
            if value is not None and not isinstance(value, expected_type):
                raise ValueError(f"diagnostic {field_name} has an invalid type")
        object.__setattr__(self, "detail", self.detail.strip())


@dataclass(frozen=True, slots=True)
class BestPriceOutcome:
    """One canonical outcome paired with its deterministic best eligible quote."""

    selection: Selection
    quote: OddsQuote

    def __post_init__(self) -> None:
        if not isinstance(self.selection, Selection):
            raise ValueError("outcome selection must be Selection")
        if not isinstance(self.quote, OddsQuote):
            raise ValueError("outcome quote must be OddsQuote")
        if self.quote.selection_id != self.selection.id:
            raise ValueError("outcome quote must reference the canonical selection")
        if self.quote.market_id != self.selection.market_id:
            raise ValueError("outcome quote and selection must belong to the same market")
        if self.quote.status is not QuoteStatus.ACTIVE:
            raise ValueError("best-price outcomes require active quotes")

    @property
    def provider_id(self) -> ProviderId:
        """Expose provider attribution without duplicating quote provenance."""
        return self.quote.provider_id


@dataclass(frozen=True, slots=True)
class MarketBookFreshness:
    """Freshness envelope of the selected quotes in one canonical market book."""

    as_of: datetime
    freshness_window: timedelta
    oldest_quote_at: datetime
    newest_quote_at: datetime

    def __post_init__(self) -> None:
        as_of = normalize_datetime(self.as_of, field="market_book_freshness.as_of")
        oldest = normalize_datetime(
            self.oldest_quote_at,
            field="market_book_freshness.oldest_quote_at",
        )
        newest = normalize_datetime(
            self.newest_quote_at,
            field="market_book_freshness.newest_quote_at",
        )
        if not isinstance(self.freshness_window, timedelta) or self.freshness_window <= timedelta(
            0
        ):
            raise ValueError("freshness_window must be a positive timedelta")
        if oldest > newest:
            raise ValueError("oldest_quote_at cannot be later than newest_quote_at")
        if newest > as_of:
            raise ValueError("market-book quotes cannot lie in the future")
        if as_of - oldest > self.freshness_window:
            raise ValueError("market-book quotes must fit inside the freshness window")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "oldest_quote_at", oldest)
        object.__setattr__(self, "newest_quote_at", newest)

    @property
    def max_quote_age(self) -> timedelta:
        """Return the age of the oldest selected quote at construction time."""
        return self.as_of - self.oldest_quote_at


@dataclass(frozen=True, slots=True)
class CanonicalMarketBook:
    """Complete deterministic best-price comparison book for one canonical market."""

    event: Event
    market: Market
    expected_selection_ids: tuple[SelectionId, ...]
    outcomes: tuple[BestPriceOutcome, ...]
    freshness: MarketBookFreshness
    construction_diagnostics: tuple[MarketBookDiagnostic, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.event, Event):
            raise ValueError("market-book event must be Event")
        if not isinstance(self.market, Market):
            raise ValueError("market-book market must be Market")
        if self.market.event_id != self.event.id:
            raise ValueError("market-book market must belong to its event")
        if not isinstance(self.freshness, MarketBookFreshness):
            raise ValueError("market-book freshness must be MarketBookFreshness")

        expected = tuple(self.expected_selection_ids)
        outcomes = tuple(self.outcomes)
        diagnostics = tuple(self.construction_diagnostics)
        if len(expected) < 2:
            raise ValueError("market book requires at least two expected selections")
        if any(not isinstance(value, SelectionId) for value in expected):
            raise ValueError("expected_selection_ids must contain SelectionId values")
        if len(set(expected)) != len(expected):
            raise ValueError("expected_selection_ids must be unique")
        if any(not isinstance(value, BestPriceOutcome) for value in outcomes):
            raise ValueError("outcomes must contain BestPriceOutcome values")
        if any(not isinstance(value, MarketBookDiagnostic) for value in diagnostics):
            raise ValueError("construction_diagnostics must contain MarketBookDiagnostic values")

        actual = tuple(outcome.selection.id for outcome in outcomes)
        if len(set(actual)) != len(actual):
            raise ValueError("market-book outcomes must have unique selections")
        if set(actual) != set(expected):
            raise ValueError("market-book outcomes must cover exactly the expected selections")
        if any(outcome.selection.market_id != self.market.id for outcome in outcomes):
            raise ValueError("every market-book selection must belong to the canonical market")
        if any(outcome.quote.event_id != self.event.id for outcome in outcomes):
            raise ValueError("every market-book quote must belong to the canonical event")
        if any(outcome.quote.market_id != self.market.id for outcome in outcomes):
            raise ValueError("every market-book quote must belong to the canonical market")

        object.__setattr__(
            self,
            "expected_selection_ids",
            tuple(sorted(expected, key=lambda value: value.value)),
        )
        object.__setattr__(
            self,
            "outcomes",
            tuple(sorted(outcomes, key=lambda value: value.selection.id.value)),
        )
        object.__setattr__(self, "construction_diagnostics", diagnostics)

    @property
    def quotes(self) -> tuple[OddsQuote, ...]:
        """Return selected quotes in canonical selection order."""
        return tuple(outcome.quote for outcome in self.outcomes)


@dataclass(frozen=True, slots=True)
class MarketBookBatch:
    """Deterministic books plus diagnostics for rejected quotes and markets."""

    books: tuple[CanonicalMarketBook, ...]
    diagnostics: tuple[MarketBookDiagnostic, ...]

    def __post_init__(self) -> None:
        books = tuple(self.books)
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(value, CanonicalMarketBook) for value in books):
            raise ValueError("books must contain CanonicalMarketBook values")
        if any(not isinstance(value, MarketBookDiagnostic) for value in diagnostics):
            raise ValueError("diagnostics must contain MarketBookDiagnostic values")
        keys = [(book.event.id, book.market.id) for book in books]
        if len(set(keys)) != len(keys):
            raise ValueError("batch may contain at most one book per event/market")
        object.__setattr__(self, "books", books)
        object.__setattr__(self, "diagnostics", diagnostics)
