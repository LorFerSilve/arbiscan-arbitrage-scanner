"""Phase-10 unit coverage for live quote state and provider polling controls."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    Provider,
    ProviderId,
    ProviderKind,
    QuoteId,
    QuoteStatus,
    SelectionId,
    Sport,
)
from arbiscan.ingestion import (
    LiveQuoteStore,
    ProviderRateGate,
    QuoteStoreDiagnosticCode,
    RealtimeIngestionPolicy,
    RealtimeIngestionRuntime,
)
from arbiscan.providers.errors import ProviderError, ProviderErrorKind
from arbiscan.providers.fake import FakeProvider, FakeProviderFixtures
from arbiscan.providers.models import ProviderOperation, RateLimitSnapshot
from arbiscan.providers.resilience import ProviderCallPolicy

AS_OF = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _quote(
    *,
    price: str = "2.10",
    source_seconds: int = 0,
    ingested_seconds: int = 0,
    quote_suffix: str = "a",
    status: QuoteStatus = QuoteStatus.ACTIVE,
) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:{quote_suffix}"),
        provider_id=ProviderId("provider:alpha"),
        event_id=EventId("event:test"),
        market_id=MarketId("market:test"),
        selection_id=SelectionId("selection:test"),
        decimal_price=Decimal(price),
        source_event_id="source:event",
        source_market_id="source:market",
        source_selection_id="source:selection",
        source_timestamp=AS_OF + timedelta(seconds=source_seconds),
        ingested_at=AS_OF + timedelta(seconds=ingested_seconds),
        status=status,
        trace_id=f"trace:{quote_suffix}",
    )


def test_quote_store_versions_updates_and_deduplicates_semantic_repeats() -> None:
    policy = RealtimeIngestionPolicy(clock_skew_tolerance=timedelta(seconds=5))
    store = LiveQuoteStore(policy)

    first = _quote(quote_suffix="first")
    added = store.apply((first,), observed_at=AS_OF)
    assert added.added_count == 1
    assert added.accepted[0].revision == 1

    duplicate = _quote(quote_suffix="transport-repeat")
    repeated = store.apply((duplicate,), observed_at=AS_OF + timedelta(seconds=1))
    assert repeated.duplicate_count == 1
    assert repeated.accepted == ()
    assert QuoteStoreDiagnosticCode.DUPLICATE in {
        diagnostic.code for diagnostic in repeated.diagnostics
    }

    changed = _quote(
        price="2.20",
        source_seconds=2,
        ingested_seconds=2,
        quote_suffix="changed",
    )
    updated = store.apply((changed,), observed_at=AS_OF + timedelta(seconds=2))
    assert updated.updated_count == 1
    assert updated.accepted[0].revision == 2
    assert store.fresh_quotes(as_of=AS_OF + timedelta(seconds=2)) == (changed,)


def test_out_of_order_quote_beyond_skew_tolerance_is_rejected() -> None:
    policy = RealtimeIngestionPolicy(clock_skew_tolerance=timedelta(seconds=2))
    store = LiveQuoteStore(policy)
    current = _quote(
        price="2.20",
        source_seconds=10,
        ingested_seconds=10,
        quote_suffix="current",
    )
    store.apply((current,), observed_at=AS_OF + timedelta(seconds=10))

    old = _quote(
        price="9.00",
        source_seconds=1,
        ingested_seconds=11,
        quote_suffix="old",
    )
    result = store.apply((old,), observed_at=AS_OF + timedelta(seconds=11))

    assert result.rejected_count == 1
    assert QuoteStoreDiagnosticCode.OUT_OF_ORDER in {
        diagnostic.code for diagnostic in result.diagnostics
    }
    assert store.fresh_quotes(as_of=AS_OF + timedelta(seconds=11)) == (current,)


def test_small_future_source_clock_skew_is_stored_but_not_actionable_until_time_catches_up() -> None:
    policy = RealtimeIngestionPolicy(clock_skew_tolerance=timedelta(seconds=5))
    store = LiveQuoteStore(policy)
    future = _quote(source_seconds=3, quote_suffix="future-small")

    result = store.apply((future,), observed_at=AS_OF)

    assert result.accepted
    assert QuoteStoreDiagnosticCode.CLOCK_SKEW_DETECTED in {
        diagnostic.code for diagnostic in result.diagnostics
    }
    assert store.fresh_quotes(as_of=AS_OF) == ()
    assert store.fresh_quotes(as_of=AS_OF + timedelta(seconds=3)) == (future,)


def test_excessive_future_source_clock_skew_fails_closed() -> None:
    policy = RealtimeIngestionPolicy(clock_skew_tolerance=timedelta(seconds=2))
    store = LiveQuoteStore(policy)
    future = _quote(source_seconds=30, quote_suffix="future-large")

    result = store.apply((future,), observed_at=AS_OF)

    assert result.rejected_count == 1
    assert len(store) == 0
    assert QuoteStoreDiagnosticCode.CLOCK_SKEW_EXCEEDED in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_stale_and_inactive_versions_are_evicted() -> None:
    policy = RealtimeIngestionPolicy(freshness_window=timedelta(seconds=30))
    store = LiveQuoteStore(policy)
    stale = _quote(quote_suffix="stale")
    inactive = OddsQuote(
        id=QuoteId("quote:inactive"),
        provider_id=ProviderId("provider:beta"),
        event_id=EventId("event:test"),
        market_id=MarketId("market:test"),
        selection_id=SelectionId("selection:other"),
        decimal_price=Decimal("2.20"),
        source_event_id="source:event",
        source_market_id="source:market",
        source_selection_id="source:other",
        source_timestamp=AS_OF + timedelta(seconds=20),
        ingested_at=AS_OF + timedelta(seconds=20),
        status=QuoteStatus.SUSPENDED,
        trace_id="trace:inactive",
    )
    store.apply((stale,), observed_at=AS_OF)
    store.apply((inactive,), observed_at=AS_OF + timedelta(seconds=20))

    eviction = store.evict_stale(as_of=AS_OF + timedelta(seconds=31))

    assert len(eviction.evicted) == 2
    assert len(store) == 0
    assert {diagnostic.code for diagnostic in eviction.diagnostics} == {
        QuoteStoreDiagnosticCode.STALE_EVICTED,
        QuoteStoreDiagnosticCode.INACTIVE_EVICTED,
    }


def test_provider_rate_gate_uses_reset_and_retry_after_metadata() -> None:
    provider_id = ProviderId("provider:rate")
    gate = ProviderRateGate(timedelta(seconds=10))
    snapshot = RateLimitSnapshot(
        provider_id=provider_id,
        observed_at=AS_OF,
        limit=100,
        remaining=0,
        resets_at=AS_OF + timedelta(seconds=30),
    )

    gate.observe(snapshot, as_of=AS_OF)
    assert gate.is_throttled(provider_id, as_of=AS_OF + timedelta(seconds=29))
    assert not gate.is_throttled(provider_id, as_of=AS_OF + timedelta(seconds=30))

    gate.observe_retry_after(provider_id, timedelta(seconds=60), as_of=AS_OF)
    assert gate.next_allowed_at(provider_id) == AS_OF + timedelta(seconds=60)


def test_runtime_skips_provider_when_rate_limit_metadata_is_exhausted() -> None:
    provider = Provider(
        id=ProviderId("provider:limited"),
        name="Limited",
        kind=ProviderKind.SYNTHETIC,
    )
    adapter = FakeProvider(
        provider=provider,
        fixtures=FakeProviderFixtures(sports=(Sport.FOOTBALL,)),
        rate_limit=RateLimitSnapshot(
            provider_id=provider.id,
            observed_at=AS_OF,
            limit=10,
            remaining=0,
            resets_at=AS_OF + timedelta(minutes=1),
        ),
        scripted_failures={
            ProviderOperation.SUPPORTED_SPORTS: (
                ProviderError(
                    provider_id=provider.id,
                    operation=ProviderOperation.SUPPORTED_SPORTS.value,
                    kind=ProviderErrorKind.INTERNAL,
                    message="must never be reached while throttled",
                ),
            )
        },
    )
    runtime = RealtimeIngestionRuntime(
        policy=RealtimeIngestionPolicy(),
        provider_call_policy=ProviderCallPolicy(max_attempts=1),
        clock=MutableClock(AS_OF),
    )

    result = asyncio.run(runtime.poll_once((adapter,), Sport.FOOTBALL))

    assert result.ingestion.snapshots == ()
    assert result.ingestion.issues == ()
    assert result.provider_metrics[0].throttled is True
    assert result.throttling_events == 1


def test_partial_provider_failure_is_isolated_from_healthy_provider() -> None:
    healthy_provider = Provider(
        id=ProviderId("provider:healthy"),
        name="Healthy",
        kind=ProviderKind.SYNTHETIC,
    )
    failing_provider = Provider(
        id=ProviderId("provider:failing"),
        name="Failing",
        kind=ProviderKind.SYNTHETIC,
    )
    healthy = FakeProvider(
        provider=healthy_provider,
        fixtures=FakeProviderFixtures(sports=(Sport.FOOTBALL,)),
    )
    failing = FakeProvider(
        provider=failing_provider,
        fixtures=FakeProviderFixtures(sports=(Sport.FOOTBALL,)),
        scripted_failures={
            ProviderOperation.SUPPORTED_SPORTS: (
                ProviderError(
                    provider_id=failing_provider.id,
                    operation=ProviderOperation.SUPPORTED_SPORTS.value,
                    kind=ProviderErrorKind.UPSTREAM,
                    message="temporary outage",
                    retryable=False,
                ),
            )
        },
    )
    runtime = RealtimeIngestionRuntime(
        policy=RealtimeIngestionPolicy(max_concurrency=2),
        provider_call_policy=ProviderCallPolicy(max_attempts=1),
        clock=MutableClock(AS_OF),
    )

    result = asyncio.run(runtime.poll_once((failing, healthy), Sport.FOOTBALL))

    assert len(result.ingestion.issues) == 1
    metrics = {metric.provider_id: metric for metric in result.provider_metrics}
    assert metrics[healthy_provider.id].issue_count == 0
    assert metrics[failing_provider.id].issue_count == 1
    health = {item.provider_id: item for item in result.provider_health}
    assert health[healthy_provider.id].consecutive_failures == 0
    assert health[failing_provider.id].consecutive_failures == 1


def test_policy_rejects_invalid_concurrency() -> None:
    try:
        RealtimeIngestionPolicy(max_concurrency=0)
    except ValueError as error:
        assert "max_concurrency" in str(error)
    else:
        raise AssertionError("invalid max_concurrency should be rejected")
