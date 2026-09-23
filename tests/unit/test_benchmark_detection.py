"""The performance harness must compare identical semantic workloads."""

from scripts.benchmark_detection import run_benchmark


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
