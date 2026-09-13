"""Phase 6 fixture-based end-to-end proof using The Odds API's real V4 schema."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from arbiscan.domain import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventStatus,
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    Participant,
    ParticipantId,
    ParticipantKind,
    ProviderId,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
)
from arbiscan.matching import CanonicalRegistry, StaticCanonicalIdHooks
from arbiscan.providers.the_odds_api import TheOddsApiConfig, TheOddsApiProvider
from arbiscan.services import run_vertical_slice
from tests.support.the_odds_api import FixtureHttpTransport

INGESTED_AT = datetime(2026, 9, 20, 11, 5, tzinfo=UTC)
LIVE_EVALUATED_AT = INGESTED_AT + timedelta(seconds=1)
EVENT_START = datetime(2026, 9, 20, 14, 0, tzinfo=UTC)


def _registry_and_hooks() -> tuple[CanonicalRegistry, StaticCanonicalIdHooks]:
    competition = Competition(
        id=CompetitionId("competition:phase6:epl"),
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
    )
    arsenal = Participant(
        id=ParticipantId("participant:phase6:arsenal"),
        sport=Sport.FOOTBALL,
        name="Arsenal",
        kind=ParticipantKind.TEAM,
    )
    chelsea = Participant(
        id=ParticipantId("participant:phase6:chelsea"),
        sport=Sport.FOOTBALL,
        name="Chelsea",
        kind=ParticipantKind.TEAM,
    )
    event = Event(
        id=EventId("event:phase6:arsenal-chelsea"),
        sport=Sport.FOOTBALL,
        competition=competition,
        participants=(arsenal, chelsea),
        scheduled_start=EVENT_START,
        status=EventStatus.SCHEDULED,
    )
    market = Market(
        id=MarketId("market:phase6:1x2"),
        event_id=event.id,
        kind=MarketKind.MATCH_WINNER_3_WAY,
        period=MarketPeriod.REGULATION,
    )
    home = Selection(
        id=SelectionId("selection:phase6:home"),
        market_id=market.id,
        kind=SelectionKind.PARTICIPANT,
        participant_id=arsenal.id,
    )
    draw = Selection(
        id=SelectionId("selection:phase6:draw"),
        market_id=market.id,
        kind=SelectionKind.DRAW,
    )
    away = Selection(
        id=SelectionId("selection:phase6:away"),
        market_id=market.id,
        kind=SelectionKind.PARTICIPANT,
        participant_id=chelsea.id,
    )
    registry = CanonicalRegistry(
        competitions=(competition,),
        participants=(arsenal, chelsea),
        events=(event,),
        markets=(market,),
        selections=(home, draw, away),
    )
    hooks = StaticCanonicalIdHooks(
        competition_ids={"soccer_epl": competition.id},
        event_ids={"epl-arsenal-chelsea-20260920": event.id},
        market_ids={
            "pinnacle:pinnacle-h2h": market.id,
            "unibet_eu:unibet-h2h": market.id,
        },
        selection_ids={
            ("pinnacle:pinnacle-h2h", "p-home"): home.id,
            ("pinnacle:pinnacle-h2h", "p-draw"): draw.id,
            ("pinnacle:pinnacle-h2h", "p-away"): away.id,
            ("unibet_eu:unibet-h2h", "u-home"): home.id,
            ("unibet_eu:unibet-h2h", "u-draw"): draw.id,
            ("unibet_eu:unibet-h2h", "u-away"): away.id,
        },
    )
    return registry, hooks


def test_recorded_real_schema_reaches_canonical_opportunity_in_live_mode() -> None:
    registry, hooks = _registry_and_hooks()
    adapter = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture"),
        transport=FixtureHttpTransport(),
        canonical_id_hooks=hooks,
        clock=lambda: INGESTED_AT,
    )

    result = asyncio.run(
        run_vertical_slice(
            adapters=(adapter,),
            registry=registry,
            sport=Sport.FOOTBALL,
            freshness_window=timedelta(minutes=2),
            clock=lambda: LIVE_EVALUATED_AT,
        )
    )

    assert result.ingestion.issues == ()
    assert result.normalization_issues == ()
    assert result.book_issues == ()
    assert len(result.evaluations) == 1
    assert len(result.opportunities) == 1
    assert result.opportunities[0].detected_at == LIVE_EVALUATED_AT
    assert all(quote.ingested_at <= result.opportunities[0].detected_at for quote in result.quotes)

    evaluation = result.evaluations[0]
    selected = {quote.selection_id: quote for quote in evaluation.quotes}
    assert selected[SelectionId("selection:phase6:home")].provider_id == ProviderId(
        "bookmaker:the-odds-api:unibet_eu"
    )
    assert selected[SelectionId("selection:phase6:draw")].provider_id == ProviderId(
        "bookmaker:the-odds-api:pinnacle"
    )
    assert selected[SelectionId("selection:phase6:away")].provider_id == ProviderId(
        "bookmaker:the-odds-api:unibet_eu"
    )
    assert all(
        quote.raw_source_reference is not None
        and quote.raw_source_reference.startswith("source://provider:the-odds-api/")
        for quote in evaluation.quotes
    )
