"""Phase 16.8 staged-enable and rollback closure regressions."""

from __future__ import annotations

import asyncio

from arbiscan.domain import ProviderId, Sport
from arbiscan.ingestion import RealtimeIngestionPolicy
from arbiscan.providers.oddspapi import ODDSPAPI_PROVIDER_ID
from arbiscan.providers.the_odds_api import THE_ODDS_API_PROVIDER_ID
from arbiscan.services import RealtimeScanner, TransportSourceEnablementPolicy
from tests.integration import test_phase16_5_real_provider_semantics as phase16_5
from tests.integration import test_phase16_6_real_multisource_coexistence as phase16_6
from tests.integration import test_phase16_7_operational_observability as phase16_7


def _scanner(
    *,
    harness: phase16_7._Harness,
    clock: phase16_7._MutableClock,
    source_policy: TransportSourceEnablementPolicy,
) -> RealtimeScanner:
    policy = RealtimeIngestionPolicy(
        freshness_window=phase16_5.FRESHNESS_WINDOW,
        max_concurrency=2,
    )
    return RealtimeScanner(
        adapters=harness.adapters,
        registry=harness.registry,
        sport=Sport.FOOTBALL,
        policy=policy,
        source_enablement_policy=source_policy,
        clock=clock,
    )


def _transport_ids(cycle: object) -> set[ProviderId]:
    from arbiscan.services import RealtimeScanCycle

    if not isinstance(cycle, RealtimeScanCycle):
        raise AssertionError("expected RealtimeScanCycle")
    return {quote.transport_provider_id or quote.provider_id for quote in cycle.fresh_quotes}


def test_primary_only_stage_does_not_poll_or_execute_disabled_second_source() -> None:
    clock = phase16_7._MutableClock(phase16_5.AS_OF)
    harness = phase16_7._real_harness(clock)
    source_policy = TransportSourceEnablementPolicy.primary_only(THE_ODDS_API_PROVIDER_ID)
    scanner = _scanner(
        harness=harness,
        clock=clock,
        source_policy=source_policy,
    )

    cycle = asyncio.run(scanner.run_cycle())

    assert set(scanner.configured_transport_provider_ids) == {
        THE_ODDS_API_PROVIDER_ID,
        ODDSPAPI_PROVIDER_ID,
    }
    assert scanner.enabled_transport_provider_ids == (THE_ODDS_API_PROVIDER_ID,)
    assert {metric.provider_id for metric in cycle.metrics.provider_metrics} == {
        THE_ODDS_API_PROVIDER_ID
    }
    assert _transport_ids(cycle) == {THE_ODDS_API_PROVIDER_ID}
    snapshot = scanner.operational_snapshot
    assert snapshot is not None
    assert {source.provider_id for source in snapshot.sources} == {THE_ODDS_API_PROVIDER_ID}


def test_dual_source_stage_activates_both_real_transports_and_shared_book() -> None:
    clock = phase16_7._MutableClock(phase16_5.AS_OF)
    harness = phase16_7._real_harness(clock)
    source_policy = TransportSourceEnablementPolicy.staged_multi_source(
        primary_provider_id=THE_ODDS_API_PROVIDER_ID,
        additional_provider_ids=frozenset({ODDSPAPI_PROVIDER_ID}),
    )
    scanner = _scanner(
        harness=harness,
        clock=clock,
        source_policy=source_policy,
    )

    cycle = asyncio.run(scanner.run_cycle())

    assert set(scanner.enabled_transport_provider_ids) == {
        THE_ODDS_API_PROVIDER_ID,
        ODDSPAPI_PROVIDER_ID,
    }
    assert {metric.provider_id for metric in cycle.metrics.provider_metrics} == {
        THE_ODDS_API_PROVIDER_ID,
        ODDSPAPI_PROVIDER_ID,
    }
    assert _transport_ids(cycle) == {
        THE_ODDS_API_PROVIDER_ID,
        ODDSPAPI_PROVIDER_ID,
    }
    assert len(cycle.fresh_quotes) == 9
    assert len(cycle.market_books) == 1

    selected = {outcome.selection.id: outcome.quote for outcome in cycle.market_books[0].outcomes}
    assert selected[phase16_5.HOME_SELECTION_ID].provider_id == phase16_6.BET365_ID
    assert selected[phase16_5.HOME_SELECTION_ID].transport_provider_id == THE_ODDS_API_PROVIDER_ID
    assert selected[phase16_5.AWAY_SELECTION_ID].provider_id == phase16_6.BETFAIR_ID
    assert selected[phase16_5.AWAY_SELECTION_ID].transport_provider_id == ODDSPAPI_PROVIDER_ID


def test_rollback_to_primary_only_removes_second_source_without_state_leakage() -> None:
    dual_clock = phase16_7._MutableClock(phase16_5.AS_OF)
    dual_harness = phase16_7._real_harness(dual_clock)
    dual_scanner = _scanner(
        harness=dual_harness,
        clock=dual_clock,
        source_policy=TransportSourceEnablementPolicy.staged_multi_source(
            primary_provider_id=THE_ODDS_API_PROVIDER_ID,
            additional_provider_ids=frozenset({ODDSPAPI_PROVIDER_ID}),
        ),
    )
    dual_cycle = asyncio.run(dual_scanner.run_cycle())
    assert ODDSPAPI_PROVIDER_ID in _transport_ids(dual_cycle)

    rollback_clock = phase16_7._MutableClock(phase16_5.AS_OF)
    rollback_harness = phase16_7._real_harness(rollback_clock)
    rollback_scanner = _scanner(
        harness=rollback_harness,
        clock=rollback_clock,
        source_policy=TransportSourceEnablementPolicy.primary_only(THE_ODDS_API_PROVIDER_ID),
    )
    rollback_cycle = asyncio.run(rollback_scanner.run_cycle())

    assert rollback_scanner.enabled_transport_provider_ids == (THE_ODDS_API_PROVIDER_ID,)
    assert _transport_ids(rollback_cycle) == {THE_ODDS_API_PROVIDER_ID}
    assert {metric.provider_id for metric in rollback_cycle.metrics.provider_metrics} == {
        THE_ODDS_API_PROVIDER_ID
    }
    snapshot = rollback_scanner.operational_snapshot
    assert snapshot is not None
    assert {source.provider_id for source in snapshot.sources} == {
        THE_ODDS_API_PROVIDER_ID
    }
    assert rollback_scanner.multisource_telemetry.material_conflicts == 0


def test_scanner_fails_closed_when_enablement_names_unconfigured_transport() -> None:
    clock = phase16_7._MutableClock(phase16_5.AS_OF)
    harness = phase16_7._real_harness(clock)
    unknown = ProviderId("transport:phase16-8:not-configured")

    try:
        _scanner(
            harness=harness,
            clock=clock,
            source_policy=TransportSourceEnablementPolicy(
                enabled_provider_ids=frozenset({THE_ODDS_API_PROVIDER_ID, unknown}),
                required_provider_ids=frozenset({THE_ODDS_API_PROVIDER_ID}),
            ),
        )
    except ValueError as exc:
        assert "enabled transport sources are not configured" in str(exc)
    else:
        raise AssertionError("unknown staged source must fail closed")
