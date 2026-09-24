"""Regression coverage for the Phase 19 provider-pipeline benchmark."""

from scripts.benchmark_provider_pipeline import run_benchmark


def test_provider_pipeline_benchmark_is_deterministic_and_accounts_for_fixtures() -> None:
    report = run_benchmark(warmup_runs=0, measured_runs=2)

    workload = report["workload"]
    assert isinstance(workload, dict)
    assert workload["fixture_providers"] == 2
    assert workload["includes_network_io"] is False

    providers = report["providers"]
    assert isinstance(providers, dict)
    the_odds_api = providers["the_odds_api"]
    oddspapi = providers["oddspapi"]
    assert isinstance(the_odds_api, dict)
    assert isinstance(oddspapi, dict)

    assert the_odds_api["adapter_requests_per_run"] == 4
    assert the_odds_api["source_markets_per_run"] == 2
    assert the_odds_api["source_selections_per_run"] == 6
    assert the_odds_api["canonical_quotes_per_run"] == 6

    assert oddspapi["adapter_requests_per_run"] == 5
    assert oddspapi["source_markets_per_run"] == 3
    assert oddspapi["source_selections_per_run"] == 3
    assert oddspapi["canonical_quotes_per_run"] == 3

    for provider_report in (the_odds_api, oddspapi):
        polling = provider_report["polling_ms"]
        normalization = provider_report["normalization_ms"]
        assert isinstance(polling, dict)
        assert isinstance(normalization, dict)
        assert polling["p95"] >= polling["median"] >= 0
        assert normalization["p95"] >= normalization["median"] >= 0
        digest = provider_report["semantic_digest"]
        assert isinstance(digest, str) and len(digest) == 64

    combined = report["combined_semantic_digest"]
    assert isinstance(combined, str) and len(combined) == 64
