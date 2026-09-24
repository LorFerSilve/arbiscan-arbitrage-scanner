"""Regression coverage for the Phase 19 event-matching benchmark."""

from scripts.benchmark_matching import run_benchmark


def test_matching_benchmark_is_deterministic_and_reports_scale() -> None:
    report = run_benchmark(events=6, warmup_runs=0, measured_runs=2)

    workload = report["workload"]
    assert isinstance(workload, dict)
    assert workload["canonical_events"] == 6
    assert workload["provider_events_per_run"] == 6
    assert workload["exhaustive_candidate_evaluations_per_cold_run"] == 36
    assert workload["indexed_candidate_evaluations_per_cold_run"] == 6
    assert workload["cached_candidate_evaluations_per_run"] == 0
    assert workload["cache_capacity"] == 6
    assert workload["cached_decisions"] == 6
    assert workload["measured_runs"] == 2

    exhaustive_cold = report["exhaustive_cold_matching_ms"]
    assert isinstance(exhaustive_cold, float) and exhaustive_cold >= 0
    indexed_cold = report["indexed_cold_matching_ms"]
    assert isinstance(indexed_cold, float) and indexed_cold >= 0
    indexed_rate = report["indexed_cold_events_per_second"]
    assert isinstance(indexed_rate, float) and indexed_rate > 0

    matching_ms = report["matching_ms"]
    assert isinstance(matching_ms, dict)
    assert matching_ms["median"] >= 0
    assert matching_ms["p95"] >= matching_ms["median"]
    assert matching_ms["max"] >= matching_ms["median"]

    rate = report["events_per_second"]
    assert isinstance(rate, float) and rate > 0

    digest = report["decision_digest"]
    assert isinstance(digest, str) and len(digest) == 64
