"""The performance harness must compare identical semantic workloads."""

from datetime import timedelta

from scripts.benchmark_detection import (
    START,
    _missing_quote_indices,
    _observations,
    _workload,
    run_benchmark,
)

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


def test_partial_transport_overlap_preserves_detection_semantics() -> None:
    single = run_benchmark(
        events=1,
        markets_per_event=1,
        providers=2,
        updates_per_cycle=2,
        warmup_cycles=0,
        measured_cycles=2,
    )
    partial = run_benchmark(
        events=1,
        markets_per_event=1,
        providers=2,
        updates_per_cycle=2,
        warmup_cycles=0,
        measured_cycles=2,
        transports_per_provider=2,
        overlap_slots=3,
    )

    assert single["market_books"] == partial["market_books"] == 2
    assert single["opportunities"] == partial["opportunities"] == 2
    assert single["result_digest"] == partial["result_digest"]
    workload = partial["workload"]
    assert isinstance(workload, dict)
    assert workload["initial_quotes"] == 6
    assert workload["overlap_slots"] == 3
    assert workload["overlap_fraction"] == 0.5
    assert workload["initial_observations"] == 9
    assert workload["measured_update_observations"] == 5
    assert workload["update_observations_per_cycle"] == 2.5
    assert partial["equivalent_overlaps"] == 6
    assert partial["conflicts"] == 0


def test_conflicts_cannot_exceed_overlapping_slots() -> None:
    try:
        run_benchmark(
            events=1,
            markets_per_event=1,
            providers=2,
            updates_per_cycle=1,
            warmup_cycles=0,
            measured_cycles=1,
            transports_per_provider=2,
            overlap_slots=1,
            conflicting_slots=2,
        )
    except ValueError as error:
        assert "overlap_slots" in str(error)
    else:
        raise AssertionError("conflicts outside overlapping slots must be rejected")


def test_distributed_unique_feed_coverage_preserves_detection_signature() -> None:
    def run(transport_count: int, mode: str) -> dict[str, object]:
        return run_benchmark(
            events=1,
            markets_per_event=2,
            providers=2,
            updates_per_cycle=4,
            warmup_cycles=0,
            measured_cycles=2,
            missing_slots=1,
            transports_per_provider=transport_count,
            overlap_slots=4 if transport_count > 1 else 0,
            coverage_mode=mode,
        )

    control = run(1, "primary")
    distributed = run(2, "distributed")
    assert distributed["result_digest"] == control["result_digest"]
    assert distributed["market_books"] == control["market_books"] == 4
    assert distributed["opportunities"] == control["opportunities"] == 4
    workload = distributed["workload"]
    assert isinstance(workload, dict)
    assert workload["active_quote_slots"] == 9
    assert workload["missing_slots"] == 1
    assert workload["initial_observations"] == 13
    assert workload["unique_slots_by_transport"] == (3, 2)
    assert workload["coverage_mode"] == "distributed"

    _, specs = _workload(events=1, markets_per_event=2, providers=2)
    quote = _observations(
        specs[5],
        at=START,
        revision=0,
        transports_per_provider=2,
        conflicting=False,
        overlapping=False,
        nonoverlap_transport_number=1,
    )[0]
    primary = _observations(
        specs[5],
        at=START,
        revision=0,
        transports_per_provider=1,
        conflicting=False,
    )[0]
    assert quote.transport_provider_id is not None
    assert quote.transport_provider_id.value == "transport:benchmark:1"
    assert quote.id == primary.id


def test_nonoverlapping_distributed_feeds_all_carry_unique_quotes() -> None:
    def run(transports: int, mode: str) -> dict[str, object]:
        return run_benchmark(
            events=1,
            markets_per_event=2,
            providers=2,
            updates_per_cycle=4,
            warmup_cycles=0,
            measured_cycles=2,
            transports_per_provider=transports,
            overlap_slots=0,
            coverage_mode=mode,
        )

    single = run(1, "primary")
    distributed = run(2, "distributed")
    assert distributed["result_digest"] == single["result_digest"]
    assert distributed["equivalent_overlaps"] == 0
    assert distributed["conflicts"] == 0
    workload = distributed["workload"]
    assert isinstance(workload, dict)
    assert workload["unique_slots_by_transport"] == (5, 5)
    assert workload["initial_observations"] == 10


def test_distributed_coverage_preserves_fail_closed_conflict_handling() -> None:
    def small_run() -> dict[str, object]:
        return run_benchmark(
            events=1,
            markets_per_event=1,
            providers=2,
            updates_per_cycle=2,
            warmup_cycles=0,
            measured_cycles=3,
            transports_per_provider=2,
            overlap_slots=2,
            conflicting_slots=1,
            coverage_mode="distributed",
        )

    first = small_run()
    second = small_run()
    assert first["result_digest"] == second["result_digest"]
    assert first["conflicts"] == second["conflicts"] == 3
    assert first["market_books"] == second["market_books"] == 3
    assert first["opportunities"] == second["opportunities"] == 3


def test_benchmark_rejects_invalid_feed_coverage_dimensions() -> None:
    def small_run(*, coverage_mode: str = "primary", missing_slots: int = 0) -> None:
        run_benchmark(
            events=1,
            markets_per_event=1,
            providers=2,
            updates_per_cycle=1,
            warmup_cycles=0,
            measured_cycles=1,
            transports_per_provider=2,
            coverage_mode=coverage_mode,
            missing_slots=missing_slots,
        )

    for mode, missing in (("impossible", 0), ("primary", -1), ("primary", 6)):
        try:
            small_run(coverage_mode=mode, missing_slots=missing)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid feed configuration accepted: {mode}, {missing}")


def test_dispersed_missing_mask_is_seeded_spread_and_reproducible() -> None:
    _, specs = _workload(events=8, markets_per_event=3, providers=3)
    first = _missing_quote_indices(
        specs, missing_slots=42, missing_pattern="dispersed", missing_seed=19
    )
    second = _missing_quote_indices(
        specs, missing_slots=42, missing_pattern="dispersed", missing_seed=19
    )
    changed = _missing_quote_indices(
        specs, missing_slots=42, missing_pattern="dispersed", missing_seed=20
    )
    assert first == second
    assert len(first) == 42
    assert first != changed
    assert first != frozenset(range(len(specs) - 42, len(specs)))
    assert len({specs[index].event_id for index in first}) > 1
    assert len({specs[index].provider_id for index in first}) > 1


def test_dispersed_mask_preserves_parity_and_reports_partial_coverage() -> None:
    def run(transports: int) -> dict[str, object]:
        return run_benchmark(
            events=8,
            markets_per_event=3,
            providers=3,
            updates_per_cycle=15,
            warmup_cycles=0,
            measured_cycles=3,
            transports_per_provider=transports,
            overlap_slots=42 if transports > 1 else 0,
            coverage_mode="distributed",
            missing_slots=42,
            missing_pattern="dispersed",
            missing_seed=19,
        )

    control = run(1)
    multisource = run(2)
    assert control["result_digest"] == multisource["result_digest"]
    assert control["market_books"] == multisource["market_books"]
    assert control["opportunities"] == multisource["opportunities"]
    workload = multisource["workload"]
    assert isinstance(workload, dict)
    assert workload["active_quote_slots"] == 126
    assert workload["missing_slots"] == 42
    assert workload["events_with_missing_slots"] > 1
    assert workload["partially_covered_selection_legs"] > 0
    assert workload["complete_markets_per_cycle"] + workload["incomplete_markets_per_cycle"] == 24
    assert multisource["market_books"] == 3 * workload["complete_markets_per_cycle"]
    assert multisource["opportunities"] == multisource["market_books"]


def test_missing_selection_leg_suppresses_entire_market_and_opportunity() -> None:
    _, specs = _workload(events=3, markets_per_event=2, providers=3)
    masked = _missing_quote_indices(
        specs, missing_slots=6, missing_pattern="selection", missing_seed=5
    )
    assert len(masked) == 6
    missing_selections = {specs[index].selection_id for index in masked}
    assert len(missing_selections) == 2
    assert all(
        sum(spec.selection_id == selection for spec in specs) == 3
        for selection in missing_selections
    )

    def run(transports: int) -> dict[str, object]:
        return run_benchmark(
            events=3,
            markets_per_event=2,
            providers=3,
            updates_per_cycle=5,
            warmup_cycles=0,
            measured_cycles=2,
            transports_per_provider=transports,
            overlap_slots=12 if transports > 1 else 0,
            coverage_mode="distributed",
            missing_slots=6,
            missing_pattern="selection",
            missing_seed=5,
        )

    control = run(1)
    multisource = run(2)
    assert multisource["result_digest"] == control["result_digest"]
    workload = multisource["workload"]
    assert isinstance(workload, dict)
    assert workload["fully_missing_selection_legs"] == 2
    assert workload["partially_covered_selection_legs"] == 0
    incomplete = workload["incomplete_markets_per_cycle"]
    assert isinstance(incomplete, int) and incomplete >= 1
    books = multisource["market_books"]
    complete = workload["complete_markets_per_cycle"]
    assert isinstance(books, int) and isinstance(complete, int)
    assert books == 2 * complete
    assert multisource["opportunities"] == books
    assert books < 12


def test_missing_masks_reject_invalid_seed_and_partial_selection_mask() -> None:
    _, specs = _workload(events=2, markets_per_event=2, providers=3)
    for pattern, seed, missing in (
        ("unrecognized", 0, 3),
        ("dispersed", -1, 3),
        ("selection", 0, 4),
    ):
        try:
            _missing_quote_indices(
                specs,
                missing_slots=missing,
                missing_pattern=pattern,
                missing_seed=seed,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid missing mask accepted: {pattern}/{seed}/{missing}")

def test_conflict_injection_skips_masked_overlapping_quote_slots() -> None:
    _, specs = _workload(events=1, markets_per_event=1, providers=2)
    missing = _missing_quote_indices(
        specs, missing_slots=1, missing_pattern="dispersed", missing_seed=10
    )
    assert missing == frozenset((0,))

    result = run_benchmark(
        events=1,
        markets_per_event=1,
        providers=2,
        updates_per_cycle=2,
        warmup_cycles=0,
        measured_cycles=2,
        transports_per_provider=2,
        overlap_slots=2,
        conflicting_slots=1,
        coverage_mode="distributed",
        missing_slots=1,
        missing_pattern="dispersed",
        missing_seed=10,
    )
    assert result["conflicts"] == 2
    workload = result["workload"]
    assert isinstance(workload, dict)
    assert workload["conflicting_slots"] == 1
    assert workload["missing_slots"] == 1


def test_conflicts_reject_insufficient_unmasked_overlap() -> None:
    try:
        run_benchmark(
            events=1,
            markets_per_event=1,
            providers=2,
            updates_per_cycle=2,
            warmup_cycles=0,
            measured_cycles=2,
            transports_per_provider=2,
            overlap_slots=2,
            conflicting_slots=2,
            missing_slots=1,
            missing_pattern="dispersed",
            missing_seed=10,
        )
    except ValueError as error:
        assert "unmasked overlapping" in str(error)
    else:
        raise AssertionError("insufficient active overlap must reject conflict injection")
