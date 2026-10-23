"""Correctness checks for replaying temporary multi-source feed outages."""

from scripts.benchmark_feed_recovery import run_feed_recovery


def _phases(report: dict[str, object], scenario: str) -> list[dict[str, object]]:
    scenarios = report["scenarios"]
    assert isinstance(scenarios, tuple)
    for item in scenarios:
        assert isinstance(item, dict)
        if item["name"] == scenario:
            phases = item["phases"]
            assert isinstance(phases, list)
            return phases
    raise AssertionError(f"missing scenario {scenario}")


def test_feed_recovery_has_deterministic_correctness_digest() -> None:
    a = run_feed_recovery()
    b = run_feed_recovery()
    assert a["all_invariants_passed"] is True
    assert a["freshness_seconds"] == 30
    assert a["scenario_count"] == 3
    assert a["result_digest"] == b["result_digest"]
    assert a["scenarios"] == b["scenarios"]


def test_essential_feed_dropout_expires_and_restores_market() -> None:
    report = run_feed_recovery()
    phases = _phases(report, "essential_feed")
    assert [phase["phase"] for phase in phases] == [
        "healthy",
        "silent_but_fresh",
        "expired",
        "evicted",
        "late_stale_packet",
        "recovered",
    ]
    assert [phase["market_books"] for phase in phases] == [2, 2, 1, 1, 1, 2]
    assert [phase["opportunities"] for phase in phases] == [2, 2, 1, 1, 1, 2]
    assert phases[2]["stale_versions"] == 2
    assert phases[3]["evicted_versions"] == 2
    assert phases[3]["stale_versions"] == 0
    assert phases[4]["stale_versions"] == 1
    assert phases[4]["fresh_quotes"] == 8
    assert phases[5]["stale_versions"] == 0
    assert phases[5]["fresh_quotes"] == 10
    assert phases[2]["market_ids"] == phases[4]["market_ids"]
    assert phases[0]["market_ids"] == phases[5]["market_ids"]


def test_redundant_transport_preserves_market_during_secondary_outage() -> None:
    report = run_feed_recovery()
    phases = _phases(report, "redundant_feed")
    assert [phase["phase"] for phase in phases] == [
        "healthy",
        "silent_but_fresh",
        "expired",
        "evicted",
        "recovered",
    ]
    assert [phase["market_books"] for phase in phases] == [2, 2, 2, 2, 2]
    assert [phase["opportunities"] for phase in phases] == [2, 2, 2, 2, 2]
    assert phases[2]["stale_versions"] == 2
    assert phases[3]["evicted_versions"] == 2
    assert phases[2]["fresh_quotes"] == 10
    assert phases[4]["fresh_quotes"] == 10
    assert phases[0]["market_ids"] == phases[4]["market_ids"]


def test_conflicting_same_time_quotes_fail_closed_and_then_recover() -> None:
    report = run_feed_recovery()
    phases = _phases(report, "conflict_then_recovery")
    assert [phase["phase"] for phase in phases] == [
        "healthy",
        "equal_time_conflict",
        "resolved",
    ]
    assert [phase["market_books"] for phase in phases] == [2, 1, 2]
    assert [phase["opportunities"] for phase in phases] == [2, 1, 2]
    assert [phase["conflicts"] for phase in phases] == [0, 2, 0]
    assert phases[0]["market_ids"] == phases[2]["market_ids"]
    assert phases[1]["market_ids"] != phases[0]["market_ids"]
