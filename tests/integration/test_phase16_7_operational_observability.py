"""Phase 16.7 operational observability regressions for both real source adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal

from arbiscan.domain import OddsQuote, ProviderId, Sport
from arbiscan.ingestion import (
    RealtimeIngestionPolicy,
    RealtimeIngestionRuntime,
)
from arbiscan.matching import CanonicalRegistry, MatchedCanonicalIdHooks
from arbiscan.observability import HealthState, assess_health
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.http import AsyncHttpTransport, HttpResponse
from arbiscan.providers.models import ProviderHealthState
from arbiscan.providers.oddspapi import ODDSPAPI_PROVIDER_ID, OddsPapiConfig, OddsPapiProvider
from arbiscan.providers.the_odds_api import (
    THE_ODDS_API_PROVIDER_ID,
    TheOddsApiConfig,
    TheOddsApiProvider,
)
from arbiscan.services import RealtimeScanner
from tests.integration import test_phase16_5_real_provider_semantics as phase16_5
from tests.integration import test_phase16_6_real_multisource_coexistence as phase16_6
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as TheOddsApiFixtureTransport


class _MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


@dataclass(slots=True)
class _ConcurrencyProbe:
    active: int = 0
    max_active: int = 0


class _ProbedTransport:
    def __init__(self, delegate: AsyncHttpTransport, probe: _ConcurrencyProbe) -> None:
        self._delegate = delegate
        self._probe = probe

    async def get(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        self._probe.active += 1
        self._probe.max_active = max(self._probe.max_active, self._probe.active)
        await asyncio.sleep(0)
        try:
            return await self._delegate.get(
                url=url,
                query=query,
                timeout_seconds=timeout_seconds,
            )
        finally:
            self._probe.active -= 1


@dataclass(frozen=True, slots=True)
class _Harness:
    registry: CanonicalRegistry
    adapters: tuple[ProviderAdapter, ...]


def _real_harness(
    clock: _MutableClock,
    *,
    odds_account_fixture: str = "account.json",
    unmatched_the_odds: bool = False,
    probe: _ConcurrencyProbe | None = None,
) -> _Harness:
    registry = phase16_5._registry()
    observations = phase16_6._load_observations()

    hooks_by_provider: dict[ProviderId, MatchedCanonicalIdHooks] = {}
    for observation in observations:
        hooks, _decision = phase16_6._hooks_for_observation(observation, registry)
        hooks_by_provider[observation.adapter.provider.id] = hooks

    if unmatched_the_odds:
        matched = hooks_by_provider[THE_ODDS_API_PROVIDER_ID]
        hooks_by_provider[THE_ODDS_API_PROVIDER_ID] = MatchedCanonicalIdHooks(
            base=matched.base,
            event_decisions={},
        )

    the_odds_transport: AsyncHttpTransport = TheOddsApiFixtureTransport(
        fixture_overrides={
            "events": "events_soccer_epl_phase16_5.json",
            "odds": "odds_event_phase16_6.json",
        }
    )
    oddspapi_transport: AsyncHttpTransport = OddsPapiFixtureTransport(
        fixture_overrides={
            "/odds": "odds_fixture_phase16_6.json",
            "/account": odds_account_fixture,
        }
    )
    if probe is not None:
        the_odds_transport = _ProbedTransport(the_odds_transport, probe)
        oddspapi_transport = _ProbedTransport(oddspapi_transport, probe)

    adapters: tuple[ProviderAdapter, ...] = (
        TheOddsApiProvider(
            config=TheOddsApiConfig(api_key="fixture"),
            transport=the_odds_transport,
            canonical_id_hooks=hooks_by_provider[THE_ODDS_API_PROVIDER_ID],
            clock=clock,
        ),
        OddsPapiProvider(
            config=OddsPapiConfig(api_key="fixture"),
            transport=oddspapi_transport,
            canonical_id_hooks=hooks_by_provider[ODDSPAPI_PROVIDER_ID],
            clock=clock,
        ),
    )
    return _Harness(registry=registry, adapters=adapters)


def _scanner(
    harness: _Harness,
    clock: _MutableClock,
    *,
    max_concurrency: int = 2,
    poll_interval: timedelta = timedelta(seconds=5),
) -> RealtimeScanner:
    policy = RealtimeIngestionPolicy(
        poll_interval=poll_interval,
        freshness_window=phase16_5.FRESHNESS_WINDOW,
        max_concurrency=max_concurrency,
        clock_skew_tolerance=timedelta(seconds=5),
        rate_limit_fallback_cooldown=timedelta(seconds=5),
    )
    return RealtimeScanner(
        adapters=harness.adapters,
        registry=harness.registry,
        sport=Sport.FOOTBALL,
        policy=policy,
        clock=clock,
    )


def test_real_sources_publish_complete_per_transport_operational_snapshot() -> None:
    clock = _MutableClock(phase16_5.AS_OF)
    scanner = _scanner(_real_harness(clock), clock)

    cycle = asyncio.run(scanner.run_cycle())
    snapshot = scanner.operational_snapshot
    assert snapshot is not None
    assert snapshot.observed_at == phase16_5.AS_OF
    assert snapshot.poll_interval == timedelta(seconds=5)
    assert snapshot.max_concurrency == 2

    sources = {source.provider_id: source for source in snapshot.sources}
    assert set(sources) == {THE_ODDS_API_PROVIDER_ID, ODDSPAPI_PROVIDER_ID}

    the_odds = sources[THE_ODDS_API_PROVIDER_ID]
    oddspapi = sources[ODDSPAPI_PROVIDER_ID]
    for source in (the_odds, oddspapi):
        assert source.health_state is ProviderHealthState.HEALTHY
        assert source.available is True
        assert source.request_count == 1
        assert source.error_count == 0
        assert source.rate_limit_event_count == 0
        assert source.last_attempt_at == phase16_5.AS_OF
        assert source.last_success_at == phase16_5.AS_OF
        assert source.last_update_at == phase16_5.AS_OF
        assert source.consecutive_failures == 0
        assert source.last_issue_count == 0
        assert source.fresh_observation_count == 6
        assert len(source.fresh_observation_age_seconds) == 6
        assert all(
            0 <= age <= phase16_5.FRESHNESS_WINDOW.total_seconds()
            for age in source.fresh_observation_age_seconds
        )
        assert source.normalization_failure_count == 0
        assert source.matching_failure_count == 0

    assert the_odds.rate_limit_remaining == 487
    assert oddspapi.rate_limit_remaining == 377
    assert len(cycle.fresh_quotes) == 9


def test_unmatched_real_source_is_attributed_without_degrading_transport_health() -> None:
    clock = _MutableClock(phase16_5.AS_OF)
    scanner = _scanner(
        _real_harness(clock, unmatched_the_odds=True),
        clock,
    )

    cycle = asyncio.run(scanner.run_cycle())
    metrics = scanner.metrics_registry.snapshot()
    snapshot = scanner.operational_snapshot
    assert snapshot is not None
    sources = {source.provider_id: source for source in snapshot.sources}

    assert metrics.provider_normalization_failures[THE_ODDS_API_PROVIDER_ID] == 1
    assert metrics.provider_matching_failures[THE_ODDS_API_PROVIDER_ID] == 1
    assert metrics.provider_normalization_failures.get(ODDSPAPI_PROVIDER_ID, 0) == 0
    assert metrics.provider_matching_failures.get(ODDSPAPI_PROVIDER_ID, 0) == 0

    the_odds = sources[THE_ODDS_API_PROVIDER_ID]
    oddspapi = sources[ODDSPAPI_PROVIDER_ID]
    assert the_odds.normalization_failure_count == 1
    assert the_odds.matching_failure_count == 1
    assert the_odds.health_state is ProviderHealthState.HEALTHY
    assert oddspapi.health_state is ProviderHealthState.HEALTHY
    assert {issue.provider_id for issue in cycle.normalization_issues} == {
        THE_ODDS_API_PROVIDER_ID
    }
    assert {quote.transport_provider_id for quote in cycle.fresh_quotes} == {
        ODDSPAPI_PROVIDER_ID
    }


def test_exhausted_oddspapi_quota_degrades_only_that_transport() -> None:
    clock = _MutableClock(phase16_5.AS_OF)
    scanner = _scanner(
        _real_harness(
            clock,
            odds_account_fixture="account_exhausted_phase16_7.json",
        ),
        clock,
    )

    cycle = asyncio.run(scanner.run_cycle())
    snapshot = scanner.operational_snapshot
    assert snapshot is not None
    sources = {source.provider_id: source for source in snapshot.sources}
    the_odds = sources[THE_ODDS_API_PROVIDER_ID]
    oddspapi = sources[ODDSPAPI_PROVIDER_ID]

    assert the_odds.health_state is ProviderHealthState.HEALTHY
    assert the_odds.error_count == 0
    assert the_odds.fresh_observation_count == 6

    assert oddspapi.health_state is ProviderHealthState.DEGRADED
    assert oddspapi.request_count == 1
    assert oddspapi.error_count == 1
    assert oddspapi.rate_limit_event_count == 1
    assert oddspapi.rate_limit_remaining == 0
    assert oddspapi.last_success_at is None
    assert oddspapi.last_update_at is None
    assert oddspapi.fresh_observation_count == 0

    health = assess_health(scanner.metrics_registry.snapshot())
    assert health.providers[THE_ODDS_API_PROVIDER_ID] is HealthState.HEALTHY
    assert health.providers[ODDSPAPI_PROVIDER_ID] is HealthState.DEGRADED
    assert health.system is HealthState.DEGRADED
    assert health.ready is True
    assert {quote.transport_provider_id for quote in cycle.fresh_quotes} == {
        THE_ODDS_API_PROVIDER_ID
    }


def test_adr0012_conflict_is_attributed_to_both_real_transports() -> None:
    registry, _observations, quotes = phase16_6._real_quotes()
    clock = _MutableClock(phase16_5.AS_OF)
    scanner = RealtimeScanner(
        adapters=(),
        registry=registry,
        sport=Sport.FOOTBALL,
        policy=RealtimeIngestionPolicy(
            freshness_window=phase16_5.FRESHNESS_WINDOW,
        ),
        clock=clock,
    )
    store = scanner.multisource_store
    assert store is not None

    the_odds = phase16_6._quote(
        quotes,
        transport_provider_id=THE_ODDS_API_PROVIDER_ID,
        price_provider_id=phase16_5.PINNACLE_ID,
        selection_id=phase16_5.HOME_SELECTION_ID,
    )
    oddspapi = phase16_6._quote(
        quotes,
        transport_provider_id=ODDSPAPI_PROVIDER_ID,
        price_provider_id=phase16_5.PINNACLE_ID,
        selection_id=phase16_5.HOME_SELECTION_ID,
    )
    timestamp = phase16_5.AS_OF - timedelta(seconds=30)
    conflicting: tuple[OddsQuote, ...] = (
        replace(
            the_odds,
            source_timestamp=timestamp,
            ingested_at=phase16_5.AS_OF,
        ),
        replace(
            oddspapi,
            decimal_price=the_odds.decimal_price + Decimal("0.10"),
            source_timestamp=timestamp,
            ingested_at=phase16_5.AS_OF,
        ),
    )
    store.apply(conflicting, observed_at=phase16_5.AS_OF)

    cycle = asyncio.run(scanner.run_cycle())
    snapshot = scanner.operational_snapshot
    assert snapshot is not None
    sources = {source.provider_id: source for source in snapshot.sources}

    assert cycle.fresh_quotes == ()
    assert scanner.multisource_telemetry.last_material_conflict_count == 1
    assert sources[THE_ODDS_API_PROVIDER_ID].overlap_diagnostic_count == 1
    assert sources[THE_ODDS_API_PROVIDER_ID].material_conflict_count == 1
    assert sources[ODDSPAPI_PROVIDER_ID].overlap_diagnostic_count == 1
    assert sources[ODDSPAPI_PROVIDER_ID].material_conflict_count == 1


def test_real_adapter_polling_respects_configured_concurrency_bound() -> None:
    clock = _MutableClock(phase16_5.AS_OF)
    probe = _ConcurrencyProbe()
    harness = _real_harness(clock, probe=probe)
    policy = RealtimeIngestionPolicy(
        freshness_window=phase16_5.FRESHNESS_WINDOW,
        max_concurrency=1,
    )
    runtime = RealtimeIngestionRuntime(policy=policy, clock=clock)

    batch = asyncio.run(runtime.poll_once(harness.adapters, Sport.FOOTBALL))

    assert probe.max_active == 1
    assert {snapshot.provider.id for snapshot in batch.ingestion.snapshots} == {
        THE_ODDS_API_PROVIDER_ID,
        ODDSPAPI_PROVIDER_ID,
    }
    assert batch.ingestion.issues == ()


def test_real_source_polling_cadence_and_update_interval_are_deterministic() -> None:
    clock = _MutableClock(phase16_5.AS_OF)
    harness = _real_harness(clock)
    scanner = _scanner(
        harness,
        clock,
        poll_interval=timedelta(seconds=7),
    )
    sleep_calls: list[float] = []

    async def advancing_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock.advance(seconds)

    async def collect_two_cycles() -> tuple[datetime, datetime]:
        cycles = scanner.cycles(sleep=advancing_sleep)
        first = await cycles.__anext__()
        second = await cycles.__anext__()
        await cycles.aclose()
        return first.metrics.started_at, second.metrics.started_at

    first_started, second_started = asyncio.run(collect_two_cycles())

    assert sleep_calls == [7.0]
    assert second_started - first_started == timedelta(seconds=7)
    snapshot = scanner.operational_snapshot
    assert snapshot is not None
    sources = {source.provider_id: source for source in snapshot.sources}
    assert sources[THE_ODDS_API_PROVIDER_ID].update_interval == timedelta(seconds=7)
    assert sources[ODDSPAPI_PROVIDER_ID].update_interval == timedelta(seconds=7)
    assert snapshot.poll_interval == timedelta(seconds=7)
