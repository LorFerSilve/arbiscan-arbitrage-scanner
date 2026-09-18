"""Tests for explicit Phase 5 source-to-canonical identity mappings."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal

from arbiscan.domain import (
    EventId,
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    ParticipantId,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
)
from arbiscan.matching import CanonicalRegistry
from arbiscan.providers.synthetic import build_phase5_synthetic_scenario


def _assert_registry_error(factory: Callable[[], CanonicalRegistry], expected: str) -> None:
    try:
        factory()
    except ValueError as error:
        assert expected in str(error)
    else:
        raise AssertionError("expected CanonicalRegistry to reject invalid graph")


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


def test_registry_rejects_unknown_participant_selection_reference() -> None:
    scenario = build_phase5_synthetic_scenario()
    selection = scenario.registry.selections[0]
    invalid = replace(selection, participant_id=ParticipantId("participant:unknown"))
    selections = (invalid, *scenario.registry.selections[1:])

    _assert_registry_error(
        lambda: CanonicalRegistry(
            competitions=scenario.registry.competitions,
            participants=scenario.registry.participants,
            events=scenario.registry.events,
            markets=scenario.registry.markets,
            selections=selections,
        ),
        "unknown participant",
    )


def test_registry_rejects_participant_from_another_event() -> None:
    scenario = build_phase5_synthetic_scenario()
    selection = scenario.registry.selections[0]
    another_event_participant = next(
        participant
        for participant in scenario.registry.participants
        if participant.id.value == "participant:everton"
    )
    invalid = replace(selection, participant_id=another_event_participant.id)
    selections = (invalid, *scenario.registry.selections[1:])

    _assert_registry_error(
        lambda: CanonicalRegistry(
            competitions=scenario.registry.competitions,
            participants=scenario.registry.participants,
            events=scenario.registry.events,
            markets=scenario.registry.markets,
            selections=selections,
        ),
        "outside its event",
    )


def test_registry_requires_exact_over_under_completeness_for_totals() -> None:
    scenario = build_phase5_synthetic_scenario()
    event_id = scenario.registry.events[0].id
    market = Market(
        id=MarketId("market:test:total:2.5"),
        event_id=event_id,
        kind=MarketKind.TOTAL_POINTS,
        period=MarketPeriod.REGULATION,
        line=Decimal("2.5"),
    )
    over = Selection(
        id=SelectionId("selection:test:over:2.5"),
        market_id=market.id,
        kind=SelectionKind.OVER,
    )
    under = Selection(
        id=SelectionId("selection:test:under:2.5"),
        market_id=market.id,
        kind=SelectionKind.UNDER,
    )

    valid = CanonicalRegistry(
        competitions=scenario.registry.competitions,
        participants=scenario.registry.participants,
        events=scenario.registry.events,
        markets=(*scenario.registry.markets, market),
        selections=(*scenario.registry.selections, over, under),
    )
    assert valid.selection_ids_for_market(market.id) == tuple(
        sorted((over.id, under.id), key=lambda value: value.value)
    )

    _assert_registry_error(
        lambda: CanonicalRegistry(
            competitions=scenario.registry.competitions,
            participants=scenario.registry.participants,
            events=scenario.registry.events,
            markets=(*scenario.registry.markets, market),
            selections=(*scenario.registry.selections, over),
        ),
        "exactly one OVER and one UNDER",
    )
