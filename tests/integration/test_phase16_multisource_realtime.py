"""Phase-16.2 realtime overlap and conflict integration regressions."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from arbiscan.domain import OddsQuote, ProviderId, QuoteId, QuoteStatus
from arbiscan.ingestion import MultiSourceLiveQuoteStore, RealtimeIngestionPolicy
from arbiscan.providers.synthetic import SyntheticScenario, build_phase5_synthetic_scenario
from arbiscan.services import RealtimeScanner


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _quote(
    *,
    scenario: SyntheticScenario,
    transport: str,
    price: str,
    seconds_old: int,
    suffix: str,
) -> OddsQuote:
    market = scenario.registry.markets[0]
    selection = next(
        selection for selection in scenario.registry.selections if selection.market_id == market.id
    )
    timestamp = scenario.as_of - timedelta(seconds=seconds_old)
    return OddsQuote(
        id=QuoteId(f"quote:{transport}:{suffix}"),
        provider_id=ProviderId("bookmaker:shared"),
        transport_provider_id=ProviderId(f"transport:{transport}"),
        event_id=market.event_id,
        market_id=market.id,
        selection_id=selection.id,
        decimal_price=Decimal(price),
        source_event_id=f"{transport}:event",
        source_market_id=f"{transport}:market",
        source_selection_id=f"{transport}:selection",
        source_timestamp=timestamp,
        ingested_at=timestamp,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{transport}:{suffix}",
    )


def _scanner() -> tuple[SyntheticScenario, RealtimeScanner, MultiSourceLiveQuoteStore]:
    scenario = build_phase5_synthetic_scenario()
    policy = RealtimeIngestionPolicy(
        freshness_window=scenario.freshness_window,
        clock_skew_tolerance=timedelta(seconds=5),
    )
    scanner = RealtimeScanner(
        adapters=(),
        registry=scenario.registry,
        sport=scenario.registry.events[0].sport,
        policy=policy,
        clock=FixedClock(scenario.as_of),
    )
    store = scanner.multisource_store
    assert isinstance(store, MultiSourceLiveQuoteStore)
    return scenario, scanner, store


def test_realtime_scanner_consolidates_same_bookmaker_across_transports() -> None:
    scenario, scanner, store = _scanner()
    alpha = _quote(
        scenario=scenario, transport="alpha", price="2.20", seconds_old=0, suffix="a"
    )
    beta = _quote(
        scenario=scenario, transport="beta", price="2.20", seconds_old=0, suffix="b"
    )
    store.apply((alpha, beta), observed_at=scenario.as_of)

    cycle = asyncio.run(scanner.run_cycle())

    assert len(store.fresh_observations(as_of=scenario.as_of)) == 2
    assert cycle.fresh_quotes == (alpha,)
    telemetry = scanner.multisource_telemetry
    assert telemetry.last_equivalent_overlap_count == 1
    assert telemetry.last_material_conflict_count == 0
    assert scanner.log_sink.records[-1].event == "scanner.multisource.consolidation"


def test_realtime_scanner_suppresses_equal_time_material_conflict() -> None:
    scenario, scanner, store = _scanner()
    alpha = _quote(
        scenario=scenario, transport="alpha", price="2.20", seconds_old=0, suffix="a"
    )
    beta = _quote(
        scenario=scenario, transport="beta", price="2.30", seconds_old=0, suffix="b"
    )
    store.apply((alpha, beta), observed_at=scenario.as_of)

    cycle = asyncio.run(scanner.run_cycle())

    assert len(store.fresh_observations(as_of=scenario.as_of)) == 2
    assert cycle.fresh_quotes == ()
    telemetry = scanner.multisource_telemetry
    assert telemetry.last_material_conflict_count == 1
    assert telemetry.material_conflicts == 1
    assert len(telemetry.last_diagnostics) == 1
    assert scanner.log_sink.records[-1].fields["material_conflict_count"] == 1


def test_realtime_scanner_prefers_newer_transport_observation() -> None:
    scenario, scanner, store = _scanner()
    older = _quote(
        scenario=scenario, transport="alpha", price="2.10", seconds_old=10, suffix="old"
    )
    newer = _quote(
        scenario=scenario, transport="beta", price="2.25", seconds_old=0, suffix="new"
    )
    store.apply((older, newer), observed_at=scenario.as_of)

    cycle = asyncio.run(scanner.run_cycle())

    assert cycle.fresh_quotes == (newer,)
    assert scanner.multisource_telemetry.last_material_conflict_count == 0
