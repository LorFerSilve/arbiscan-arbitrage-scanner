"""Tests for explicit Phase 5 source-to-canonical identity mappings."""

import asyncio

from arbiscan.domain import EventId, MarketId, SelectionId, Sport
from arbiscan.providers import build_phase5_synthetic_scenario


def test_registry_exposes_complete_three_way_market_identity() -> None:
    scenario = build_phase5_synthetic_scenario()
    market_id = MarketId("market:phase5:arb:1x2")

    assert scenario.registry.event(EventId("event:phase5:arb")) is not None
    assert scenario.registry.selection_ids_for_market(market_id) == (
        SelectionId("selection:phase5:arb:away"),
        SelectionId("selection:phase5:arb:draw"),
        SelectionId("selection:phase5:arb:home"),
    )


def test_provider_hooks_do_not_guess_unmapped_lookalike_event() -> None:
    scenario = build_phase5_synthetic_scenario()
    beta = next(
        adapter
        for adapter in scenario.adapters
        if adapter.provider.id.value == "provider:synthetic-beta"
    )
    hooks = beta.canonical_id_hooks
    assert hooks is not None

    competitions = asyncio.run(beta.discover_competitions(Sport.FOOTBALL))
    events = asyncio.run(beta.discover_events(competitions[0].external_id))
    mismatch_event = next(event for event in events if event.external_id == "beta:lookalike")
    assert hooks.event_id(mismatch_event) is None
