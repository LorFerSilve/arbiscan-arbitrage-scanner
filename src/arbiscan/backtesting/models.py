"""Immutable historical replay and backtesting models for Phase 18."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

from arbiscan.arbitrage import ArbitrageEvaluation
from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    Opportunity,
    ProviderId,
)
from arbiscan.domain.serialization import dumps
from arbiscan.ingestion.multisource import SourceObservationKey
from arbiscan.lifecycle import ActionabilityPolicy, LifecycleEvaluation, LifecycleState
from arbiscan.marketbook import ProviderBookPolicy


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _non_negative_timedelta(value: timedelta, *, field: str) -> timedelta:
    if not isinstance(value, timedelta) or value.total_seconds() < 0:
        raise ValueError(f"{field} must be a non-negative timedelta")
    return value


def _finite_decimal(value: Decimal, *, field: str, minimum: Decimal = Decimal("0")) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")
    if value < minimum:
        raise ValueError(f"{field} cannot be below {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class HistoricalQuoteBatch:
    """Canonical quote updates that became available together at one replay instant."""

    observed_at: datetime
    quotes: tuple[OddsQuote, ...]

    def __post_init__(self) -> None:
        observed = _aware_utc(self.observed_at, field="historical_batch.observed_at")
        quotes = tuple(self.quotes)
        if not quotes:
            raise ValueError("historical quote batch cannot be empty")
        if any(not isinstance(quote, OddsQuote) for quote in quotes):
            raise ValueError("historical quote batch must contain OddsQuote values")
        keys = tuple(SourceObservationKey.from_quote(quote) for quote in quotes)
        if len(set(keys)) != len(keys):
            raise ValueError(
                "historical quote batch may contain at most one update per SourceObservationKey"
            )
        if any(quote.ingested_at > observed for quote in quotes):
            raise ValueError("historical quote cannot be available before its ingestion timestamp")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(
            self,
            "quotes",
            tuple(
                sorted(
                    quotes,
                    key=lambda quote: (
                        quote.provider_id.value,
                        (quote.transport_provider_id or quote.provider_id).value,
                        quote.event_id.value,
                        quote.market_id.value,
                        quote.selection_id.value,
                        quote.id.value,
                    ),
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class HistoricalQuoteCorpus:
    """Deterministic normalized quote corpus used for reproducible replay."""

    batches: tuple[HistoricalQuoteBatch, ...]

    def __post_init__(self) -> None:
        batches = tuple(self.batches)
        if not batches:
            raise ValueError("historical quote corpus cannot be empty")
        if any(not isinstance(batch, HistoricalQuoteBatch) for batch in batches):
            raise ValueError("historical quote corpus must contain HistoricalQuoteBatch values")

        previous: datetime | None = None
        seen_quote_ids: dict[object, OddsQuote] = {}
        for batch in batches:
            if previous is not None and batch.observed_at <= previous:
                raise ValueError("historical quote batches must be strictly chronological")
            previous = batch.observed_at
            for quote in batch.quotes:
                existing = seen_quote_ids.get(quote.id)
                if existing is not None and existing != quote:
                    raise ValueError(
                        "historical corpus reuses one quote ID for different canonical content"
                    )
                seen_quote_ids[quote.id] = quote
        object.__setattr__(self, "batches", batches)

    @classmethod
    def from_quotes(cls, quotes: tuple[OddsQuote, ...]) -> HistoricalQuoteCorpus:
        """Group canonical quotes by ingestion time into a deterministic corpus."""
        values = tuple(quotes)
        if not values:
            raise ValueError("quotes cannot be empty")
        if any(not isinstance(quote, OddsQuote) for quote in values):
            raise ValueError("quotes must contain OddsQuote values")

        grouped: dict[datetime, list[OddsQuote]] = {}
        for quote in values:
            grouped.setdefault(quote.ingested_at.astimezone(UTC), []).append(quote)
        return cls(
            batches=tuple(
                HistoricalQuoteBatch(observed_at=at, quotes=tuple(grouped[at]))
                for at in sorted(grouped)
            )
        )

    @property
    def digest(self) -> str:
        """Stable SHA-256 over replay times and canonical serialized quote payloads."""
        digest = sha256()
        for batch in self.batches:
            digest.update(batch.observed_at.isoformat().encode("utf-8"))
            digest.update(b"\n")
            for quote in batch.quotes:
                digest.update(dumps(quote).encode("utf-8"))
                digest.update(b"\n")
        return digest.hexdigest()

    @property
    def providers(self) -> tuple[ProviderId, ...]:
        return tuple(
            sorted(
                {quote.provider_id for batch in self.batches for quote in batch.quotes},
                key=lambda value: value.value,
            )
        )


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Replay assumptions that must remain explicit in every Phase-18 report."""

    freshness_window: timedelta
    detection_latency: timedelta = timedelta(0)
    clock_skew_tolerance: timedelta = timedelta(seconds=5)
    minimum_profit_margin: Decimal = Decimal("0")
    provider_policy: ProviderBookPolicy | None = None
    actionability_policy: ActionabilityPolicy | None = None
    market_ids: tuple[MarketId, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.freshness_window, timedelta) or self.freshness_window <= timedelta(
            0
        ):
            raise ValueError("freshness_window must be a positive timedelta")
        _non_negative_timedelta(self.detection_latency, field="detection_latency")
        _non_negative_timedelta(self.clock_skew_tolerance, field="clock_skew_tolerance")
        _finite_decimal(self.minimum_profit_margin, field="minimum_profit_margin")
        if self.provider_policy is not None and not isinstance(
            self.provider_policy, ProviderBookPolicy
        ):
            raise ValueError("provider_policy must be ProviderBookPolicy when present")
        if self.actionability_policy is not None and not isinstance(
            self.actionability_policy, ActionabilityPolicy
        ):
            raise ValueError("actionability_policy must be ActionabilityPolicy when present")
        if self.market_ids is not None:
            values = tuple(self.market_ids)
            if any(not isinstance(value, MarketId) for value in values):
                raise ValueError("market_ids must contain MarketId values")
            if len(set(values)) != len(values):
                raise ValueError("market_ids must be unique")
            object.__setattr__(
                self,
                "market_ids",
                tuple(sorted(values, key=lambda value: value.value)),
            )


@dataclass(frozen=True, slots=True)
class ReplayDetection:
    """One theoretical arbitrage detection at a simulated detector instant."""

    detected_at: datetime
    opportunity: Opportunity
    evaluation: ArbitrageEvaluation
    lifecycle: LifecycleEvaluation | None
    selected_provider_ids: tuple[ProviderId, ...]
    max_quote_age: timedelta

    def __post_init__(self) -> None:
        detected = _aware_utc(self.detected_at, field="replay_detection.detected_at")
        if not isinstance(self.opportunity, Opportunity):
            raise ValueError("replay detection opportunity must be Opportunity")
        if not isinstance(self.evaluation, ArbitrageEvaluation):
            raise ValueError("replay detection evaluation must be ArbitrageEvaluation")
        if self.lifecycle is not None and not isinstance(self.lifecycle, LifecycleEvaluation):
            raise ValueError("replay detection lifecycle must be LifecycleEvaluation when present")
        providers = tuple(self.selected_provider_ids)
        if any(not isinstance(value, ProviderId) for value in providers):
            raise ValueError("selected_provider_ids must contain ProviderId values")
        if len(set(providers)) != len(providers):
            raise ValueError("selected_provider_ids must be unique")
        if not isinstance(self.max_quote_age, timedelta) or self.max_quote_age < timedelta(0):
            raise ValueError("max_quote_age must be a non-negative timedelta")
        object.__setattr__(self, "detected_at", detected)
        object.__setattr__(
            self,
            "selected_provider_ids",
            tuple(sorted(providers, key=lambda value: value.value)),
        )

    @property
    def actionable(self) -> bool:
        return self.lifecycle is not None and self.lifecycle.state is LifecycleState.ACTIONABLE


@dataclass(frozen=True, slots=True)
class OpportunityInterval:
    """Contiguous replay interval during which one canonical market remained arbitrage."""

    event_id: EventId
    market_id: MarketId
    started_at: datetime
    ended_at: datetime
    detection_count: int
    max_theoretical_profit_margin: Decimal
    ever_actionable: bool
    closed_by_end_of_stream: bool

    def __post_init__(self) -> None:
        started = _aware_utc(self.started_at, field="opportunity_interval.started_at")
        ended = _aware_utc(self.ended_at, field="opportunity_interval.ended_at")
        if ended < started:
            raise ValueError("opportunity interval cannot end before it starts")
        if type(self.detection_count) is not int or self.detection_count < 1:
            raise ValueError("opportunity interval detection_count must be >= 1")
        _finite_decimal(
            self.max_theoretical_profit_margin,
            field="opportunity_interval.max_theoretical_profit_margin",
        )
        if type(self.ever_actionable) is not bool:
            raise ValueError("opportunity interval ever_actionable must be bool")
        if type(self.closed_by_end_of_stream) is not bool:
            raise ValueError("opportunity interval closed_by_end_of_stream must be bool")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "ended_at", ended)

    @property
    def duration(self) -> timedelta:
        return self.ended_at - self.started_at


@dataclass(frozen=True, slots=True)
class StaleFalsePositive:
    """Arbitrage visible only when the configured freshness gate is relaxed."""

    detected_at: datetime
    event_id: EventId
    market_id: MarketId
    counterfactual_profit_margin: Decimal
    max_quote_age: timedelta

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "detected_at",
            _aware_utc(self.detected_at, field="stale_false_positive.detected_at"),
        )
        _finite_decimal(
            self.counterfactual_profit_margin,
            field="stale_false_positive.counterfactual_profit_margin",
        )
        if not isinstance(self.max_quote_age, timedelta) or self.max_quote_age < timedelta(0):
            raise ValueError("stale false-positive max_quote_age must be non-negative")


@dataclass(frozen=True, slots=True)
class ProviderReplayMetrics:
    """Provider-specific replay coverage and opportunity contribution metrics."""

    provider_id: ProviderId
    observed_quote_count: int
    selected_best_quote_count: int
    complete_book_count: int
    theoretical_detection_count: int
    actionable_detection_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise ValueError("provider replay metrics require ProviderId")
        for field_name in (
            "observed_quote_count",
            "selected_best_quote_count",
            "complete_book_count",
            "theoretical_detection_count",
            "actionable_detection_count",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class BacktestSummary:
    """Compact deterministic summary for comparing replay configurations."""

    corpus_digest: str
    detection_latency: timedelta
    evaluation_count: int
    theoretical_detection_count: int
    actionable_detection_count: int
    stale_false_positive_count: int
    opportunity_interval_count: int
    total_opportunity_duration: timedelta
    actionability_evaluated: bool

    def __post_init__(self) -> None:
        if not isinstance(self.corpus_digest, str) or len(self.corpus_digest) != 64:
            raise ValueError("corpus_digest must be a SHA-256 hex digest")
        _non_negative_timedelta(self.detection_latency, field="summary.detection_latency")
        if not isinstance(self.total_opportunity_duration, timedelta):
            raise ValueError("total_opportunity_duration must be timedelta")
        for field_name in (
            "evaluation_count",
            "theoretical_detection_count",
            "actionable_detection_count",
            "stale_false_positive_count",
            "opportunity_interval_count",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if type(self.actionability_evaluated) is not bool:
            raise ValueError("actionability_evaluated must be bool")


@dataclass(frozen=True, slots=True)
class BacktestReport:
    """Complete offline replay output without realized-profit claims."""

    summary: BacktestSummary
    detections: tuple[ReplayDetection, ...]
    opportunity_intervals: tuple[OpportunityInterval, ...]
    stale_false_positives: tuple[StaleFalsePositive, ...]
    provider_metrics: tuple[ProviderReplayMetrics, ...]


@dataclass(frozen=True, slots=True)
class LatencySensitivityPoint:
    """One deterministic replay result for a configured detection delay."""

    latency: timedelta
    theoretical_detection_count: int
    actionable_detection_count: int
    stale_false_positive_count: int
    opportunity_interval_count: int
    total_opportunity_duration: timedelta


@dataclass(frozen=True, slots=True)
class MatchingLabel:
    """One labeled source-event matching decision."""

    source_record_id: str
    expected_event_id: EventId | None
    predicted_event_id: EventId | None

    def __post_init__(self) -> None:
        if not isinstance(self.source_record_id, str) or not self.source_record_id.strip():
            raise ValueError("source_record_id must be non-empty text")
        if self.expected_event_id is not None and not isinstance(self.expected_event_id, EventId):
            raise ValueError("expected_event_id must be EventId when present")
        if self.predicted_event_id is not None and not isinstance(self.predicted_event_id, EventId):
            raise ValueError("predicted_event_id must be EventId when present")
        object.__setattr__(self, "source_record_id", self.source_record_id.strip())


@dataclass(frozen=True, slots=True)
class MatchingQualityMetrics:
    """Precision/recall counts for labeled event-matching decisions."""

    true_positive: int
    false_positive: int
    false_negative: int
    precision: Decimal
    recall: Decimal

    def __post_init__(self) -> None:
        for field_name in ("true_positive", "false_positive", "false_negative"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        _finite_decimal(self.precision, field="precision")
        _finite_decimal(self.recall, field="recall")
        if self.precision > Decimal("1") or self.recall > Decimal("1"):
            raise ValueError("precision and recall cannot exceed one")


@dataclass(slots=True)
class _OpenOpportunityInterval:
    """Internal mutable accumulator used only during deterministic replay."""

    event_id: EventId
    market_id: MarketId
    started_at: datetime
    last_detected_at: datetime
    detection_count: int
    max_margin: Decimal
    ever_actionable: bool
