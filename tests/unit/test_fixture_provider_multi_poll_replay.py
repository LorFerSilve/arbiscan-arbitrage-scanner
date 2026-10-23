"""Regression assertions for repeated fixture-backed two-provider polls."""

from scripts.replay_fixture_provider_polls import run_fixture_multi_poll_replay

NAMES = (
    "healthy",
    "partial_coverage",
    "essential_leg_expired",
    "late_old_revision",
    "provider_recovered",
    "future_timestamp_rejected",
    "all_providers_expired",
    "both_recovered",
)


def _phases() -> list[dict[str, object]]:
    report = run_fixture_multi_poll_replay()
    assert report["all_invariants_passed"] is True
    assert report["freshness_seconds"] == 30
    assert report["phase_count"] == len(NAMES)
    phases = report["phases"]
    assert isinstance(phases, list)
    assert tuple(phase["phase"] for phase in phases) == NAMES
    assert tuple(phase["seconds"] for phase in phases) == (0, 10, 31, 32, 40, 50, 81, 90)
    return phases


def _count(row: dict[str, object], key: str) -> int:
    value = row[key]
    assert isinstance(value, int)
    return value


def test_fixture_multi_poll_replay_has_stable_semantic_digest() -> None:
    first = run_fixture_multi_poll_replay()
    second = run_fixture_multi_poll_replay()
    assert first == second
    digest = first["result_digest"]
    assert isinstance(digest, str)
    assert len(digest) == 64
    assert first["includes_network_io"] is False


def test_missing_selection_expires_before_market_is_rebuilt() -> None:
    rows = _phases()
    assert [phase["books"] for phase in rows] == [1, 1, 0, 0, 1, 1, 0, 1]
    assert rows[1]["provider_modes"] == {
        "the_odds_api": "no_draw",
        "oddspapi": "no_draw",
    }
    assert _count(rows[2], "stale_observations") > 0
    assert _count(rows[2], "executable_quotes") > 0
    assert rows[2]["arbitrages"] == 0
    assert rows[3]["books"] == 0
    assert _count(rows[6], "executable_quotes") == 0
    assert _count(rows[6], "stale_observations") > 0
    assert _count(rows[7], "executable_quotes") > 0
    assert rows[7]["books"] == 1


def test_late_source_revision_and_skewed_snapshot_cannot_poison_live_state() -> None:
    rows = _phases()
    assert rows[3]["rejected"] == 1
    assert rows[3]["executable_quotes"] == rows[2]["executable_quotes"]
    assert rows[3]["quote_digest"] == rows[2]["quote_digest"]
    assert rows[5]["normalization_issues"] == (
        "future_snapshot",
        "future_snapshot",
    )
    assert rows[5]["books"] == 1
    assert rows[5]["material_conflicts"] == 0
    assert all(_count(phase, "arbitrages") <= _count(phase, "books") for phase in rows)
