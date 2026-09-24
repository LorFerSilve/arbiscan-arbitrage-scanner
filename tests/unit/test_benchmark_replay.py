"""The replay throughput harness must preserve deterministic report semantics."""

from scripts.benchmark_replay import run_benchmark


def test_repeated_multisource_replay_has_stable_corpus_and_report() -> None:
    arguments = {
        "events": 2,
        "markets_per_event": 2,
        "providers": 2,
        "update_batches": 2,
        "updates_per_batch": 4,
        "transports_per_provider": 2,
        "warmup_runs": 0,
        "measured_runs": 2,
    }
    first = run_benchmark(**arguments)
    second = run_benchmark(**arguments)

    assert first["workload"] == second["workload"]
    workload = first["workload"]
    assert isinstance(workload, dict)
    assert workload["observations"] == 56
    assert first["corpus_digest"] == second["corpus_digest"]
    assert first["report_signature"] == second["report_signature"]
    assert (
        first["summary"]
        == second["summary"]
        == {
            "evaluations": 12,
            "theoretical_detections": 12,
            "actionable_detections": 0,
            "stale_false_positives": 0,
            "opportunity_intervals": 4,
        }
    )
    timings = first["replay_ms"]
    assert isinstance(timings, dict)
    assert isinstance(timings["median"], float)
    assert isinstance(timings["p95"], float)
    assert isinstance(timings["max"], float)
    assert timings["median"] >= 0
    assert timings["median"] <= timings["p95"] <= timings["max"]
    assert isinstance(first["observations_per_second"], float)
    assert first["observations_per_second"] > 0


def test_conflicting_transports_suppress_incomplete_market_books() -> None:
    arguments = {
        "events": 1,
        "markets_per_event": 1,
        "providers": 1,
        "update_batches": 2,
        "updates_per_batch": 1,
        "transports_per_provider": 2,
        "warmup_runs": 0,
        "measured_runs": 1,
    }
    agreeing = run_benchmark(**arguments)
    conflict = run_benchmark(**arguments, conflicting_slots=1)
    repeated_conflict = run_benchmark(**arguments, conflicting_slots=1)

    assert agreeing["summary"] == {
        "evaluations": 3,
        "theoretical_detections": 3,
        "actionable_detections": 0,
        "stale_false_positives": 0,
        "opportunity_intervals": 1,
    }
    assert conflict["summary"] == {
        "evaluations": 0,
        "theoretical_detections": 0,
        "actionable_detections": 0,
        "stale_false_positives": 0,
        "opportunity_intervals": 0,
    }
    assert conflict["corpus_digest"] == repeated_conflict["corpus_digest"]
    assert conflict["report_signature"] == repeated_conflict["report_signature"]
    assert conflict["report_signature"] != agreeing["report_signature"]
