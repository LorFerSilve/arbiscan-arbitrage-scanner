"""Keep the diagnostic-heavy market-book benchmark deterministic."""

from scripts.benchmark_marketbook_diagnostics import run_benchmark


def test_diagnostic_benchmark_preserves_repeatable_semantics() -> None:
    def small_run() -> dict[str, object]:
        return run_benchmark(
            events=2,
            markets_per_event=2,
            providers=2,
            rejected_per_valid=1,
            warmup_runs=0,
            measured_runs=2,
        )

    first = small_run()
    second = small_run()

    assert first["market_books"] == second["market_books"] == 4
    assert first["diagnostics"] == second["diagnostics"] == 20
    assert first["result_digest"] == second["result_digest"]
    assert first["workload"] == second["workload"]


def test_diagnostic_benchmark_can_measure_clean_feed() -> None:
    result = run_benchmark(
        events=1,
        markets_per_event=1,
        providers=2,
        rejected_per_valid=0,
        warmup_runs=0,
        measured_runs=1,
    )
    assert result["market_books"] == 1
    assert result["diagnostics"] == 0
