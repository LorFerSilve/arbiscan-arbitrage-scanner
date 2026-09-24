"""The SQLite benchmark must replay the same fixed corpus on every run."""

from scripts.benchmark_persistence import run_benchmark


def test_persistence_benchmark_checks_full_and_filtered_replay() -> None:
    report = run_benchmark(
        events=2,
        selections_per_event=2,
        providers=2,
        warmup_runs=0,
        measured_runs=2,
    )

    assert report["workload"] == {
        "events": 2,
        "selections_per_event": 2,
        "providers": 2,
        "quotes": 8,
        "filtered_quotes": 4,
        "warmup_runs": 0,
        "measured_runs": 2,
    }
    assert report["corpus_sha256"] == (
        "bb5c3192355f1e21ed89a3ec87ed8d18d99bce7f4d0bf19a80b08b9009402654"
    )
    assert report["filtered_sha256"] == (
        "3169fe281403d90fe29e55aae7676cee712796b936fd74a475bc6262e73c0368"
    )
    write_rate = report["write_quotes_per_second"]
    batch_rate = report["batch_write_quotes_per_second"]
    batch_speedup = report["batch_write_speedup"]
    read_rate = report["read_quotes_per_second"]
    assert isinstance(write_rate, float) and write_rate > 0
    assert isinstance(batch_rate, float) and batch_rate > 0
    assert isinstance(batch_speedup, float) and batch_speedup > 0
    assert isinstance(read_rate, float) and read_rate > 0
