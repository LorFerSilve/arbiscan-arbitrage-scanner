"""Integration regressions between the strict bridge and Phase 7 odds normalization."""

import asyncio
from dataclasses import replace
from decimal import Decimal

from arbiscan.normalization import NormalizationIssueCode, normalize_source_snapshot
from arbiscan.providers.models import SourceOddsFormat
from arbiscan.providers.synthetic import build_phase5_synthetic_scenario


def test_strict_bridge_converts_fractional_source_odds_to_decimal() -> None:
    scenario = build_phase5_synthetic_scenario()
    alpha = scenario.adapters[0]
    events = asyncio.run(alpha.discover_events("alpha:epl"))
    event = next(value for value in events if value.external_id == "alpha:arb")
    snapshot = asyncio.run(alpha.fetch_odds(event.external_id))
    assert snapshot is not None

    market = snapshot.markets[0]
    home = replace(
        market.selections[0],
        price="19/10",
        odds_format=SourceOddsFormat.FRACTIONAL,
    )
    converted = replace(
        snapshot,
        markets=(replace(market, selections=(home, *market.selections[1:])),),
    )

    result = normalize_source_snapshot(
        provider=alpha.provider,
        hooks=alpha.canonical_id_hooks,
        event=event,
        snapshot=converted,
        registry=scenario.registry,
        as_of=scenario.as_of,
        freshness_window=scenario.freshness_window,
    )

    assert result.issues == ()
    assert Decimal("2.9") in {quote.decimal_price for quote in result.quotes}


def test_extreme_source_odds_are_rejected_without_aborting_the_snapshot() -> None:
    scenario = build_phase5_synthetic_scenario()
    alpha = scenario.adapters[0]
    events = asyncio.run(alpha.discover_events("alpha:epl"))
    event = next(value for value in events if value.external_id == "alpha:arb")
    snapshot = asyncio.run(alpha.fetch_odds(event.external_id))
    assert snapshot is not None

    market = snapshot.markets[0]
    extreme = replace(
        market.selections[0],
        price="1e-999999999",
        odds_format=SourceOddsFormat.IMPLIED_PROBABILITY,
    )
    converted = replace(
        snapshot,
        markets=(replace(market, selections=(extreme, *market.selections[1:])),),
    )

    result = normalize_source_snapshot(
        provider=alpha.provider,
        hooks=alpha.canonical_id_hooks,
        event=event,
        snapshot=converted,
        registry=scenario.registry,
        as_of=scenario.as_of,
        freshness_window=scenario.freshness_window,
    )

    assert len(result.quotes) == 2
    assert tuple(issue.code for issue in result.issues) == (NormalizationIssueCode.MALFORMED_PRICE,)
