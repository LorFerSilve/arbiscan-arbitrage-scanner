"""Regression coverage for the Phase 19 event-matching benchmark."""

from scripts.benchmark_matching import run_benchmark


def test_matching_benchmark_is_deterministic_and_reports_scale() -> None:
    report = run_benchmark(events=6, warmup_runs=0, measured_runs=2)

    workload = report["workload"]
    assert isinstance(workload, dict)
    assert workload["canonical_events"] == 6
    assert workload["provider_events_per_run"] == 6
    assert workload["uncached_candidate_comparisons"] == 36
    assert workload["cached_candidate_comparisons_per_run"] == 0
    assert workload["cache_capacity"] == 6
    assert workload["cached_decisions"] == 6
    assert workload["measured_runs"] == 2

    cold = report["cold_matching_ms"]
    assert isinstance(cold, float) and cold >= 0

    matching_ms = report["matching_ms"]
    assert isinstance(matching_ms, dict)
    assert matching_ms["median"] >= 0
    assert matching_ms["p95"] >= matching_ms["median"]
    assert matching_ms["max"] >= matching_ms["median"]

    rate = report["events_per_second"]
    assert isinstance(rate, float) and rate > 0

    digest = report["decision_digest"]
    assert isinstance(digest, str) and len(digest) == 64
