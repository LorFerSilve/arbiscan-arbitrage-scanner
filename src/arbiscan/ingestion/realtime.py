"""Real-time polling, quote versioning, freshness, and ingestion health control."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    ProviderId,
    QuoteStatus,
    SelectionId,
    Sport,
)
from arbiscan.ingestion.collector import IngestionBatch, IngestionIssue, collect_snapshots
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.errors import ProviderError, ProviderErrorKind
from arbiscan.providers.models import (
    ProviderCapability,
    ProviderHealthState,
    ProviderOperation,
    RateLimitSnapshot,
)
from arbiscan.providers.resilience import ProviderCallPolicy, ProviderExecutor

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _non_negative_timedelta(value: timedelta, *, field_name: str) -> timedelta:
    if not isinstance(value, timedelta):
        raise ValueError(f"{field_name} must be timedelta")
    if value.total_seconds() < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return value


@dataclass(frozen=True, slots=True)
class RealtimeIngestionPolicy:
    """Phase-10 scheduling, concurrency, freshness, and clock-skew policy."""

    poll_interval: timedelta = timedelta(seconds=5)
    freshness_window: timedelta = timedelta(minutes=2)
    max_concurrency: int = 4
    clock_skew_tolerance: timedelta = timedelta(seconds=5)
    rate_limit_fallback_cooldown: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        poll_interval = _non_negative_timedelta(
            self.poll_interval,
            field_name="poll_interval",
        )
        freshness_window = _non_negative_timedelta(
            self.freshness_window,
            field_name="freshness_window",
        )
        skew = _non_negative_timedelta(
            self.clock_skew_tolerance,
            field_name="clock_skew_tolerance",
        )
        fallback = _non_negative_timedelta(
            self.rate_limit_fallback_cooldown,
            field_name="rate_limit_fallback_cooldown",
        )
        if poll_interval.total_seconds() <= 0:
            raise ValueError("poll_interval must be greater than zero")
        if freshness_window.total_seconds() <= 0:
            raise ValueError("freshness_window must be greater than zero")
        if type(self.max_concurrency) is not int or self.max_concurrency < 1:
            raise ValueError("max_concurrency must be an integer >= 1")
        if fallback.total_seconds() <= 0:
            raise ValueError("rate_limit_fallback_cooldown must be greater than zero")
        object.__setattr__(self, "poll_interval", poll_interval)
        object.__setattr__(self, "freshness_window", freshness_window)
        object.__setattr__(self, "clock_skew_tolerance", skew)
        object.__setattr__(self, "rate_limit_fallback_cooldown", fallback)


@dataclass(frozen=True, slots=True, order=True)
class QuoteKey:
    """Stable live identity for one provider/canonical outcome quote."""

    provider_id: ProviderId
    event_id: EventId
    market_id: MarketId
    selection_id: SelectionId

    @classmethod
    def from_quote(cls, quote: OddsQuote) -> QuoteKey:
        return cls(
            provider_id=quote.provider_id,
            event_id=quote.event_id,
            market_id=quote.market_id,
            selection_id=quote.selection_id,
        )


@dataclass(frozen=True, slots=True)
class QuoteVersion:
    """Current accepted revision for one live quote key."""

    key: QuoteKey
    revision: int
    quote: OddsQuote
    observed_at: datetime

    def __post_init__(self) -> None:
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("quote revision must be an integer >= 1")
        if not isinstance(self.quote, OddsQuote):
            raise ValueError("quote version quote must be OddsQuote")
        if self.key != QuoteKey.from_quote(self.quote):
            raise ValueError("quote version key must match quote canonical identity")
        object.__setattr__(
            self,
            "observed_at",
            _aware_utc(self.observed_at, field_name="quote_version.observed_at"),
        )

    @property
    def effective_timestamp(self) -> datetime:
        return self.quote.source_timestamp or self.quote.ingested_at


class QuoteStoreDiagnosticCode(StrEnum):
    """Stable Phase-10 quote-state diagnostic reasons."""

    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    FUTURE_INGESTION = "future_ingestion"
    CLOCK_SKEW_DETECTED = "clock_skew_detected"
    CLOCK_SKEW_EXCEEDED = "clock_skew_exceeded"
    STALE_EVICTED = "stale_evicted"
    INACTIVE_EVICTED = "inactive_evicted"


@dataclass(frozen=True, slots=True)
class QuoteStoreDiagnostic:
    code: QuoteStoreDiagnosticCode
    key: QuoteKey
    detail: str


@dataclass(frozen=True, slots=True)
class QuoteStoreApplyResult:
    """Deterministic result of one quote-store update batch."""

    accepted: tuple[QuoteVersion, ...] = field(default_factory=tuple)
    diagnostics: tuple[QuoteStoreDiagnostic, ...] = field(default_factory=tuple)
    added_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    rejected_count: int = 0


@dataclass(frozen=True, slots=True)
class QuoteStoreEvictionResult:
    evicted: tuple[QuoteVersion, ...]
    diagnostics: tuple[QuoteStoreDiagnostic, ...]


class LiveQuoteStore:
    """In-memory current-state store with deterministic deduplication/versioning."""

    def __init__(self, policy: RealtimeIngestionPolicy) -> None:
        if not isinstance(policy, RealtimeIngestionPolicy):
            raise ValueError("policy must be RealtimeIngestionPolicy")
        self._policy = policy
        self._current: dict[QuoteKey, QuoteVersion] = {}

    @property
    def policy(self) -> RealtimeIngestionPolicy:
        return self._policy

    def __len__(self) -> int:
        return len(self._current)

    @staticmethod
    def _fingerprint(quote: OddsQuote) -> tuple[object, ...]:
        effective_timestamp = quote.source_timestamp or quote.ingested_at
        return (
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
    def _sort_key(quote: OddsQuote) -> tuple[str, str, str, str, datetime, datetime, str]:
        effective = quote.source_timestamp or quote.ingested_at
        return (
            quote.provider_id.value,
            quote.event_id.value,
            quote.market_id.value,
            quote.selection_id.value,
            effective,
            quote.ingested_at,
            quote.id.value,
        )

    def apply(
        self,
        quotes: Iterable[OddsQuote],
        *,
        observed_at: datetime,
    ) -> QuoteStoreApplyResult:
        """Apply canonical quotes while rejecting impossible/far-out-of-order updates."""
        observed = _aware_utc(observed_at, field_name="observed_at")
        quote_values = tuple(quotes)
        if any(not isinstance(quote, OddsQuote) for quote in quote_values):
            raise ValueError("quotes must contain OddsQuote values")

        accepted: list[QuoteVersion] = []
        diagnostics: list[QuoteStoreDiagnostic] = []
        added_count = 0
        updated_count = 0
        duplicate_count = 0
        rejected_count = 0

        for quote in sorted(quote_values, key=self._sort_key):
            key = QuoteKey.from_quote(quote)
            effective = quote.source_timestamp or quote.ingested_at

            if quote.ingested_at > observed:
                diagnostics.append(
                    QuoteStoreDiagnostic(
                        code=QuoteStoreDiagnosticCode.FUTURE_INGESTION,
                        key=key,
                        detail="quote was ingested after the live-store observation time",
                    )
                )
                rejected_count += 1
                continue

            future_delta = effective - observed
            if future_delta > self._policy.clock_skew_tolerance:
                diagnostics.append(
                    QuoteStoreDiagnostic(
                        code=QuoteStoreDiagnosticCode.CLOCK_SKEW_EXCEEDED,
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
                    QuoteStoreDiagnostic(
                        code=QuoteStoreDiagnosticCode.CLOCK_SKEW_DETECTED,
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
                        QuoteStoreDiagnostic(
                            code=QuoteStoreDiagnosticCode.OUT_OF_ORDER,
                            key=key,
                            detail=(
                                "incoming quote effective timestamp is older than the current "
                                "version beyond the clock-skew tolerance"
                            ),
                        )
                    )
                    rejected_count += 1
                    continue

                if self._fingerprint(current.quote) == self._fingerprint(quote):
                    diagnostics.append(
                        QuoteStoreDiagnostic(
                            code=QuoteStoreDiagnosticCode.DUPLICATE,
                            key=key,
                            detail=(
                                "incoming quote does not change the current semantic quote state"
                            ),
                        )
                    )
                    duplicate_count += 1
                    continue

                if effective < current_effective and quote.ingested_at <= current.quote.ingested_at:
                    diagnostics.append(
                        QuoteStoreDiagnostic(
                            code=QuoteStoreDiagnosticCode.OUT_OF_ORDER,
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

            version = QuoteVersion(
                key=key,
                revision=revision,
                quote=quote,
                observed_at=observed,
            )
            self._current[key] = version
            accepted.append(version)

        return QuoteStoreApplyResult(
            accepted=tuple(accepted),
            diagnostics=tuple(
                sorted(
                    diagnostics,
                    key=lambda item: (
                        item.key.provider_id.value,
                        item.key.event_id.value,
                        item.key.market_id.value,
                        item.key.selection_id.value,
                        item.code.value,
                    ),
                )
            ),
            added_count=added_count,
            updated_count=updated_count,
            duplicate_count=duplicate_count,
            rejected_count=rejected_count,
        )

    def fresh_versions(self, *, as_of: datetime) -> tuple[QuoteVersion, ...]:
        """Return only quotes that are actionable under Phase-10 freshness policy."""
        moment = _aware_utc(as_of, field_name="as_of")
        values: list[QuoteVersion] = []
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
                ),
            )
        )

    def fresh_quotes(self, *, as_of: datetime) -> tuple[OddsQuote, ...]:
        return tuple(version.quote for version in self.fresh_versions(as_of=as_of))

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
        fresh = self.fresh_versions(as_of=moment)
        if not fresh:
            return None
        return max(moment - version.effective_timestamp for version in fresh)

    def evict_stale(self, *, as_of: datetime) -> QuoteStoreEvictionResult:
        """Remove inactive or expired versions so failed providers cannot linger forever."""
        moment = _aware_utc(as_of, field_name="as_of")
        evicted: list[QuoteVersion] = []
        diagnostics: list[QuoteStoreDiagnostic] = []
        for key, version in tuple(self._current.items()):
            effective = version.effective_timestamp
            code: QuoteStoreDiagnosticCode | None = None
            detail = ""
            if version.quote.status is not QuoteStatus.ACTIVE:
                code = QuoteStoreDiagnosticCode.INACTIVE_EVICTED
                detail = "inactive quote removed from live state"
            elif effective <= moment and moment - effective > self._policy.freshness_window:
                code = QuoteStoreDiagnosticCode.STALE_EVICTED
                detail = "quote exceeded the configured freshness window"
            if code is None:
                continue
            del self._current[key]
            evicted.append(version)
            diagnostics.append(QuoteStoreDiagnostic(code=code, key=key, detail=detail))

        return QuoteStoreEvictionResult(
            evicted=tuple(
                sorted(
                    evicted,
                    key=lambda item: (
                        item.key.event_id.value,
                        item.key.market_id.value,
                        item.key.selection_id.value,
                        item.key.provider_id.value,
                    ),
                )
            ),
            diagnostics=tuple(
                sorted(
                    diagnostics,
                    key=lambda item: (
                        item.key.provider_id.value,
                        item.key.event_id.value,
                        item.key.market_id.value,
                        item.key.selection_id.value,
                        item.code.value,
                    ),
                )
            ),
        )


class ProviderRateGate:
    """Cached provider-specific next-allowed timestamps derived from rate metadata."""

    def __init__(self, fallback_cooldown: timedelta) -> None:
        self._fallback_cooldown = _non_negative_timedelta(
            fallback_cooldown,
            field_name="fallback_cooldown",
        )
        if self._fallback_cooldown <= timedelta(0):
            raise ValueError("fallback_cooldown must be greater than zero")
        self._next_allowed_at: dict[ProviderId, datetime] = {}

    def is_throttled(self, provider_id: ProviderId, *, as_of: datetime) -> bool:
        moment = _aware_utc(as_of, field_name="as_of")
        next_allowed = self._next_allowed_at.get(provider_id)
        if next_allowed is None:
            return False
        if moment >= next_allowed:
            self._next_allowed_at.pop(provider_id, None)
            return False
        return True

    def next_allowed_at(self, provider_id: ProviderId) -> datetime | None:
        return self._next_allowed_at.get(provider_id)

    def observe(self, snapshot: RateLimitSnapshot, *, as_of: datetime) -> None:
        moment = _aware_utc(as_of, field_name="as_of")
        candidates: list[datetime] = []
        if snapshot.retry_after is not None and snapshot.retry_after > timedelta(0):
            candidates.append(moment + snapshot.retry_after)
        if snapshot.remaining == 0:
            if snapshot.resets_at is not None and snapshot.resets_at > moment:
                candidates.append(snapshot.resets_at)
            elif snapshot.retry_after is None:
                candidates.append(moment + self._fallback_cooldown)
        if candidates:
            self._next_allowed_at[snapshot.provider_id] = max(candidates)
        else:
            self._next_allowed_at.pop(snapshot.provider_id, None)

    def observe_retry_after(
        self,
        provider_id: ProviderId,
        retry_after: timedelta | None,
        *,
        as_of: datetime,
    ) -> None:
        moment = _aware_utc(as_of, field_name="as_of")
        delay = self._fallback_cooldown
        if retry_after is not None:
            delay = max(
                _non_negative_timedelta(retry_after, field_name="retry_after"),
                self._fallback_cooldown,
            )
        self._next_allowed_at[provider_id] = moment + delay


@dataclass(frozen=True, slots=True)
class ProviderPollMetrics:
    provider_id: ProviderId
    started_at: datetime
    completed_at: datetime
    snapshot_count: int
    issue_count: int
    throttled: bool
    rate_limit_remaining: int | None
    update_interval: timedelta | None
    consecutive_failures: int
    health_state: ProviderHealthState

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "started_at",
            _aware_utc(self.started_at, field_name="started_at"),
        )
        object.__setattr__(
            self,
            "completed_at",
            _aware_utc(self.completed_at, field_name="completed_at"),
        )
        if self.completed_at < self.started_at:
            raise ValueError("provider poll completed_at cannot precede started_at")

    @property
    def request_latency(self) -> timedelta:
        return self.completed_at - self.started_at


@dataclass(frozen=True, slots=True)
class ProviderIngestionHealth:
    provider_id: ProviderId
    state: ProviderHealthState
    last_attempt_at: datetime
    last_success_at: datetime | None
    last_update_at: datetime | None
    consecutive_failures: int
    throttling_events: int
    last_issue_count: int


@dataclass(slots=True)
class _MutableProviderHealth:
    state: ProviderHealthState = ProviderHealthState.HEALTHY
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_update_at: datetime | None = None
    consecutive_failures: int = 0
    throttling_events: int = 0
    last_issue_count: int = 0


class ProviderHealthTracker:
    """Track provider ingestion health without coupling live scanning to storage."""

    def __init__(self) -> None:
        self._states: dict[ProviderId, _MutableProviderHealth] = {}

    def record(
        self,
        provider_id: ProviderId,
        *,
        completed_at: datetime,
        snapshot_count: int,
        issue_count: int,
        throttled: bool,
    ) -> tuple[ProviderIngestionHealth, timedelta | None]:
        completed = _aware_utc(completed_at, field_name="completed_at")
        state = self._states.setdefault(provider_id, _MutableProviderHealth())
        previous_update = state.last_update_at
        state.last_attempt_at = completed
        state.last_issue_count = issue_count

        if throttled:
            state.state = ProviderHealthState.DEGRADED
            state.throttling_events += 1
        elif issue_count == 0:
            state.state = ProviderHealthState.HEALTHY
            state.consecutive_failures = 0
            state.last_success_at = completed
            if snapshot_count > 0:
                state.last_update_at = completed
        else:
            state.consecutive_failures += 1
            if snapshot_count > 0:
                state.state = ProviderHealthState.DEGRADED
                state.last_success_at = completed
                state.last_update_at = completed
            elif state.consecutive_failures >= 3:
                state.state = ProviderHealthState.UNAVAILABLE
            else:
                state.state = ProviderHealthState.DEGRADED

        update_interval = None
        if (
            snapshot_count > 0
            and previous_update is not None
            and state.last_update_at is not None
        ):
            update_interval = state.last_update_at - previous_update

        return self._freeze(provider_id, state), update_interval

    @staticmethod
    def _freeze(
        provider_id: ProviderId,
        state: _MutableProviderHealth,
    ) -> ProviderIngestionHealth:
        if state.last_attempt_at is None:
            raise ValueError("provider health cannot be frozen before the first attempt")
        return ProviderIngestionHealth(
            provider_id=provider_id,
            state=state.state,
            last_attempt_at=state.last_attempt_at,
            last_success_at=state.last_success_at,
            last_update_at=state.last_update_at,
            consecutive_failures=state.consecutive_failures,
            throttling_events=state.throttling_events,
            last_issue_count=state.last_issue_count,
        )

    def snapshots(self) -> tuple[ProviderIngestionHealth, ...]:
        values: list[ProviderIngestionHealth] = []
        for provider_id, state in self._states.items():
            if state.last_attempt_at is not None:
                values.append(self._freeze(provider_id, state))
        return tuple(sorted(values, key=lambda item: item.provider_id.value))


@dataclass(frozen=True, slots=True)
class RealtimeIngestionBatch:
    ingestion: IngestionBatch
    provider_metrics: tuple[ProviderPollMetrics, ...]
    provider_health: tuple[ProviderIngestionHealth, ...]

    @property
    def throttling_events(self) -> int:
        return sum(1 for metric in self.provider_metrics if metric.throttled)


@dataclass(frozen=True, slots=True)
class _ProviderPollResult:
    batch: IngestionBatch
    metric: ProviderPollMetrics


class RealtimeIngestionRuntime:
    """Bounded-concurrency provider polling with rate-limit and health control."""

    def __init__(
        self,
        *,
        policy: RealtimeIngestionPolicy | None = None,
        provider_call_policy: ProviderCallPolicy | None = None,
        clock: Clock = _utc_now,
    ) -> None:
        self.policy = policy or RealtimeIngestionPolicy()
        self.provider_call_policy = provider_call_policy
        if not callable(clock):
            raise ValueError("clock must be callable")
        self._clock = clock
        self._rate_gate = ProviderRateGate(self.policy.rate_limit_fallback_cooldown)
        self._health = ProviderHealthTracker()

    def _now(self) -> datetime:
        return _aware_utc(self._clock(), field_name="clock")

    async def poll_once(
        self,
        adapters: tuple[ProviderAdapter, ...],
        sport: Sport,
    ) -> RealtimeIngestionBatch:
        """Poll providers concurrently while preserving deterministic aggregate output."""
        if any(not isinstance(adapter, ProviderAdapter) for adapter in adapters):
            raise ValueError("adapters must contain ProviderAdapter values")
        semaphore = asyncio.Semaphore(self.policy.max_concurrency)

        async def run(adapter: ProviderAdapter) -> _ProviderPollResult:
            async with semaphore:
                return await self._poll_adapter(adapter, sport)

        results = await asyncio.gather(
            *(
                run(adapter)
                for adapter in sorted(adapters, key=lambda item: item.provider.id.value)
            )
        )

        snapshots = tuple(
            sorted(
                (snapshot for result in results for snapshot in result.batch.snapshots),
                key=lambda item: (
                    item.provider.id.value,
                    item.event.scheduled_start,
                    item.event.external_id,
                ),
            )
        )
        issues = tuple(
            sorted(
                (issue for result in results for issue in result.batch.issues),
                key=lambda item: (
                    item.provider_id.value,
                    item.operation,
                    item.external_event_id or "",
                    item.kind.value,
                ),
            )
        )
        return RealtimeIngestionBatch(
            ingestion=IngestionBatch(snapshots=snapshots, issues=issues),
            provider_metrics=tuple(
                sorted(
                    (result.metric for result in results),
                    key=lambda item: item.provider_id.value,
                )
            ),
            provider_health=self._health.snapshots(),
        )

    async def _poll_adapter(
        self,
        adapter: ProviderAdapter,
        sport: Sport,
    ) -> _ProviderPollResult:
        started_at = self._now()
        provider_id = adapter.provider.id
        if self._rate_gate.is_throttled(provider_id, as_of=started_at):
            return self._throttled_result(
                provider_id=provider_id,
                started_at=started_at,
                issues=(),
                rate_limit_remaining=None,
            )

        preflight_issues: list[IngestionIssue] = []
        rate_limit_snapshot: RateLimitSnapshot | None = None
        if adapter.capabilities.supports(ProviderCapability.RATE_LIMIT_METADATA):
            executor = ProviderExecutor(adapter, policy=self.provider_call_policy)
            try:
                rate_limit_snapshot = await executor.run(
                    ProviderOperation.RATE_LIMIT,
                    adapter.rate_limit,
                )
            except ProviderError as error:
                issue = IngestionIssue(
                    provider_id=error.provider_id,
                    operation=error.operation,
                    kind=error.kind,
                    detail=str(error),
                    retry_after=error.retry_after,
                )
                preflight_issues.append(issue)
                if error.kind is ProviderErrorKind.RATE_LIMITED:
                    self._rate_gate.observe_retry_after(
                        provider_id,
                        error.retry_after,
                        as_of=self._now(),
                    )
                    return self._throttled_result(
                        provider_id=provider_id,
                        started_at=started_at,
                        issues=tuple(preflight_issues),
                        rate_limit_remaining=None,
                    )
            else:
                if rate_limit_snapshot is not None:
                    if rate_limit_snapshot.provider_id != provider_id:
                        preflight_issues.append(
                            IngestionIssue(
                                provider_id=provider_id,
                                operation=ProviderOperation.RATE_LIMIT.value,
                                kind=ProviderErrorKind.MALFORMED_RESPONSE,
                                detail="rate-limit metadata belongs to a different provider",
                            )
                        )
                        rate_limit_snapshot = None
                    else:
                        self._rate_gate.observe(rate_limit_snapshot, as_of=self._now())
                        if self._rate_gate.is_throttled(provider_id, as_of=self._now()):
                            return self._throttled_result(
                                provider_id=provider_id,
                                started_at=started_at,
                                issues=tuple(preflight_issues),
                                rate_limit_remaining=rate_limit_snapshot.remaining,
                            )

        collected = await collect_snapshots(
            (adapter,),
            sport,
            policy=self.provider_call_policy,
        )
        issues = [*preflight_issues, *collected.issues]
        completed_at = self._now()
        encountered_throttle = False

        for issue in issues:
            if issue.kind is ProviderErrorKind.RATE_LIMITED:
                encountered_throttle = True
                self._rate_gate.observe_retry_after(
                    provider_id,
                    issue.retry_after,
                    as_of=completed_at,
                )

        health, update_interval = self._health.record(
            provider_id,
            completed_at=completed_at,
            snapshot_count=len(collected.snapshots),
            issue_count=len(issues),
            throttled=encountered_throttle,
        )
        return _ProviderPollResult(
            batch=IngestionBatch(
                snapshots=collected.snapshots,
                issues=tuple(
                    sorted(
                        issues,
                        key=lambda item: (
                            item.provider_id.value,
                            item.operation,
                            item.external_event_id or "",
                            item.kind.value,
                        ),
                    )
                ),
            ),
            metric=ProviderPollMetrics(
                provider_id=provider_id,
                started_at=started_at,
                completed_at=completed_at,
                snapshot_count=len(collected.snapshots),
                issue_count=len(issues),
                throttled=encountered_throttle,
                rate_limit_remaining=(
                    None if rate_limit_snapshot is None else rate_limit_snapshot.remaining
                ),
                update_interval=update_interval,
                consecutive_failures=health.consecutive_failures,
                health_state=health.state,
            ),
        )

    def _throttled_result(
        self,
        *,
        provider_id: ProviderId,
        started_at: datetime,
        issues: tuple[IngestionIssue, ...],
        rate_limit_remaining: int | None,
    ) -> _ProviderPollResult:
        completed_at = self._now()
        health, update_interval = self._health.record(
            provider_id,
            completed_at=completed_at,
            snapshot_count=0,
            issue_count=len(issues),
            throttled=True,
        )
        return _ProviderPollResult(
            batch=IngestionBatch(snapshots=(), issues=issues),
            metric=ProviderPollMetrics(
                provider_id=provider_id,
                started_at=started_at,
                completed_at=completed_at,
                snapshot_count=0,
                issue_count=len(issues),
                throttled=True,
                rate_limit_remaining=rate_limit_remaining,
                update_interval=update_interval,
                consecutive_failures=health.consecutive_failures,
                health_state=health.state,
            ),
        )
