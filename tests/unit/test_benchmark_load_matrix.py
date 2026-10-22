"""Regression coverage for the Phase 19 deployment load matrix."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from scripts.benchmark_load_matrix import (
    LoadProfile,
    _parser,
    load_profile_file,
    run_load_matrix,
)


def _tiny_profile() -> LoadProfile:
    return LoadProfile(
        name="tiny",
        events=2,
        markets_per_event=2,
        providers=2,
        updates_per_cycle=4,
        transports_per_provider=2,
        overlap_bps=5_000,
        warmup_cycles=0,
        measured_cycles=2,
    )


def test_load_matrix_requires_semantic_parity_and_stable_digest() -> None:
    first = run_load_matrix(profiles=(_tiny_profile(),))
    second = run_load_matrix(profiles=(_tiny_profile(),))

    assert first["profile_count"] == second["profile_count"] == 1
    assert first["all_semantic_parity"] is True
    assert second["all_semantic_parity"] is True
    assert first["matrix_digest"] == second["matrix_digest"]

    profiles = first["profiles"]
    assert isinstance(profiles, tuple) and len(profiles) == 1
    result = profiles[0]
    assert isinstance(result, dict)
    assert result["semantic_parity"] is True
    assert result["conflicts"] == 0

    profile = result["profile"]
    assert isinstance(profile, dict)
    assert profile["quote_slots"] == 20
    assert profile["overlap_slots"] == 10
    assert profile["overlap_bps"] == 5_000

    workload = result["workload"]
    assert isinstance(workload, dict)
    assert workload["initial_observations"] == 30
    assert workload["overlap_fraction"] == 0.5


def test_load_profile_rejects_invalid_overlap_basis_points() -> None:
    try:
        LoadProfile(
            name="invalid",
            events=1,
            markets_per_event=1,
            providers=1,
            updates_per_cycle=1,
            transports_per_provider=2,
            overlap_bps=10_001,
            warmup_cycles=0,
            measured_cycles=1,
        )
    except ValueError as error:
        assert "overlap_bps" in str(error)
    else:
        raise AssertionError("invalid overlap basis points must be rejected")


def test_local_aggregate_profile_matches_existing_load_matrix(tmp_path: Path) -> None:
    profile = _tiny_profile()
    path = tmp_path / "aggregate.json"
    path.write_text(json.dumps(asdict(profile)), encoding="utf-8")

    loaded = load_profile_file(path)
    assert loaded == profile
    assert (
        run_load_matrix(profiles=(loaded,))["matrix_digest"]
        == run_load_matrix(profiles=(profile,))["matrix_digest"]
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("events", True),
        ("providers", 2.5),
        ("overlap_bps", "2500"),
        ("measured_cycles", 0),
        ("name", ""),
    ],
)
def test_local_profile_rejects_invalid_values(tmp_path: Path, field: str, value: object) -> None:
    payload = asdict(_tiny_profile())
    payload[field] = value
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_profile_file(path)


def test_local_profile_rejects_secret_or_unexpected_fields(tmp_path: Path) -> None:
    payload = asdict(_tiny_profile())
    payload["api_key"] = "never-load-provider-credentials"
    path = tmp_path / "unexpected.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="raw provider records and credentials"):
        load_profile_file(path)


def test_local_profile_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        load_profile_file(path)


def test_local_profile_and_builtin_profiles_are_mutually_exclusive() -> None:
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--profile", "reference", "--profile-file", "aggregate.json"])
