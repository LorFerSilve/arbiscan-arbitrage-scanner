"""The performance harness must compare identical semantic workloads."""

from datetime import timedelta

from scripts.benchmark_detection import START, _observations, _workload, run_benchmark

from arbiscan.ingestion.multisource import ConsolidationDiagnosticCode, PriceSlotKey
from arbiscan.ingestion.multisource_state import MultiSourceLiveQuoteStore
from arbiscan.ingestion.realtime import RealtimeIngestionPolicy


def test_benchmark_workload_has_stable_detection_signature() -> None:
    def small_run() -> dict[str, object]:
        return run_benchmark(
            events=2,
            markets_per_event=2,
            providers=2,
            updates_per_cycle=4,
            warmup_cycles=0,
            measured_cycles=2,
        )

    first = small_run()
    second = small_run()

    assert first["market_books"] == second["market_books"] == 8
    assert first["opportunities"] == second["opportunities"] == 8
    assert first["result_digest"] == second["result_digest"]


def test_equivalent_transports_keep_single_source_opportunity_digest() -> None:
    def small_run(transports_per_provider: int) -> dict[str, object]:
        return run_benchmark(
            events=2,
            markets_per_event=2,
            providers=2,
            updates_per_cycle=4,
            warmup_cycles=0,
            measured_cycles=2,
            transports_per_provider=transports_per_provider,
        )

    single = small_run(1)
    overlapping = small_run(2)

    assert single["market_books"] == overlapping["market_books"] == 8
    assert single["opportunities"] == overlapping["opportunities"] == 8
    assert single["result_digest"] == overlapping["result_digest"]
    assert single["executable_quotes"] == overlapping["executable_quotes"] == 40
    assert single["equivalent_overlaps"] == 0
    assert overlapping["equivalent_overlaps"] == 40
    assert overlapping["conflicts"] == 0


def test_multisource_benchmark_keeps_equal_time_conflicts_fail_closed() -> None:
    def small_run() -> dict[str, object]:
        return run_benchmark(
            events=1,
            markets_per_event=1,
            providers=2,
            updates_per_cycle=2,
            warmup_cycles=0,
            measured_cycles=3,
            transports_per_provider=2,
            conflicting_slots=1,
        )

    first = small_run()
    second = small_run()

    workload = first["workload"]
    assert isinstance(workload, dict)
    assert workload == second["workload"]
    assert workload["initial_observations"] == 12
    assert workload["update_observations_per_cycle"] == 4
    assert first["executable_quotes"] == second["executable_quotes"] == 15
    assert first["equivalent_overlaps"] == second["equivalent_overlaps"] == 15
    assert first["conflicts"] == second["conflicts"] == 3
    assert first["market_books"] == second["market_books"] == 3
    assert first["opportunities"] == second["opportunities"] == 3
    assert first["result_digest"] == second["result_digest"]
    stage_ms = first["stage_ms"]
    assert isinstance(stage_ms, dict)
    assert "fresh_consolidate" in stage_ms

    _, specs = _workload(events=1, markets_per_event=1, providers=2)
    store = MultiSourceLiveQuoteStore(
        RealtimeIngestionPolicy(freshness_window=timedelta(minutes=5))
    )
    observations = tuple(
        quote
        for index, spec in enumerate(specs)
        for quote in _observations(
            spec,
            at=START,
            revision=0,
            transports_per_provider=2,
            conflicting=index == 0,
        )
    )
    store.apply(observations, observed_at=START)
    executable = store.fresh_quotes(as_of=START)
    conflicting_slot = PriceSlotKey.from_quote(observations[0])
    assert len(store) == 12
    assert len(executable) == 5
    assert conflicting_slot not in {PriceSlotKey.from_quote(quote) for quote in executable}
    conflicts = tuple(
        item
        for item in store.last_consolidation_result.diagnostics
        if item.code is ConsolidationDiagnosticCode.MATERIAL_CONFLICT
    )
    assert len(conflicts) == 1
    assert conflicts[0].slot == conflicting_slot


def test_conflicts_require_independent_transports() -> None:
    try:
        run_benchmark(
            events=1,
            markets_per_event=1,
            providers=2,
            updates_per_cycle=1,
            warmup_cycles=0,
            measured_cycles=1,
            conflicting_slots=1,
        )
    except ValueError as error:
        assert "at least two transports" in str(error)
    else:
        raise AssertionError("a conflict without independent transports must be rejected")
