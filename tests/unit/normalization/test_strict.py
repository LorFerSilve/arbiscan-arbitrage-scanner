"""Regression tests for strict Phase 5 normalization boundaries."""

import asyncio
from dataclasses import replace
from datetime import timedelta

from arbiscan.normalization import NormalizationIssueCode, normalize_source_snapshot
from arbiscan.providers.synthetic import build_phase5_synthetic_scenario


def test_snapshot_ingested_after_as_of_is_rejected_even_with_past_source_time() -> None:
    scenario = build_phase5_synthetic_scenario()
    alpha = scenario.adapters[0]
    events = asyncio.run(alpha.discover_events("alpha:epl"))
    event = next(value for value in events if value.external_id == "alpha:arb")
    snapshot = asyncio.run(alpha.fetch_odds(event.external_id))
    assert snapshot is not None
    future_ingestion = replace(
        snapshot,
        source_timestamp=scenario.as_of - timedelta(seconds=30),
        ingested_at=scenario.as_of + timedelta(seconds=1),
    )

    result = normalize_source_snapshot(
        provider=alpha.provider,
        hooks=alpha.canonical_id_hooks,
        event=event,
        snapshot=future_ingestion,
        registry=scenario.registry,
        as_of=scenario.as_of,
        freshness_window=scenario.freshness_window,
    )

    assert result.quotes == ()
    assert tuple(issue.code for issue in result.issues) == (
        NormalizationIssueCode.FUTURE_INGESTION,
    )
