"""Phase 17.9 end-to-end basketball spreads/totals regression."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.arbitrage import (
    CurrencyRoundingPolicy,
    allocate_stakes,
    build_opportunity,
    evaluate_market,
)
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
    OddsQuote,
    OpportunityId,
    Participant,
    ParticipantId,
    ParticipantKind,
    ProviderId,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
    StakePlanId,
)
from arbiscan.ingestion import MultiSourceLiveQuoteStore, RealtimeIngestionPolicy
from arbiscan.marketbook import build_market_books
from arbiscan.matching import CanonicalRegistry, StaticCanonicalIdHooks
from arbiscan.normalization import normalize_source_snapshot
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.models import OddsSnapshot, SourceEvent, SourceMarket, SourceSelectionQuote
from arbiscan.providers.oddspapi import OddsPapiConfig, OddsPapiProvider
from arbiscan.providers.the_odds_api import TheOddsApiConfig, TheOddsApiProvider
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as TheOddsApiFixtureTransport

AS_OF = datetime(2026, 9, 18, 13, 0, tzinfo=UTC)
START = datetime(2026, 9, 18, 19, 0, tzinfo=UTC)
FRESHNESS_WINDOW = timedelta(minutes=10)

COMPETITION_ID = CompetitionId("competition:phase17-9:nba")
EVENT_ID = EventId("event:phase17-9:celtics-knicks")
CELTICS_ID = ParticipantId("participant:phase17-9:boston-celtics")
KNICKS_ID = ParticipantId("participant:phase17-9:new-york-knicks")

TOTAL_MARKET_ID = MarketId("market:phase17-9:total:215.5")
TOTAL_OVER_ID = SelectionId("selection:phase17-9:total:over")
TOTAL_UNDER_ID = SelectionId("selection:phase17-9:total:under")

SPREAD_MARKET_ID = MarketId("market:phase17-9:spread:-3.5")
SPREAD_CELTICS_ID = SelectionId("selection:phase17-9:spread:celtics")
SPREAD_KNICKS_ID = SelectionId("selection:phase17-9:spread:knicks")

PINNACLE_ID = ProviderId("bookmaker:the-odds-api:pinnacle")
BET365_ID = ProviderId("bookmaker:the-odds-api:bet365")
BETFAIR_ID = ProviderId("bookmaker:the-odds-api:betfair")


@dataclass(frozen=True, slots=True)
class _Observation:
    adapter: ProviderAdapter
    event: SourceEvent
    snapshot: OddsSnapshot


def _registry() -> CanonicalRegistry:
    competition = Competition(
        id=COMPETITION_ID,
        sport=Sport.BASKETBALL,
        name="NBA",
        region="USA",
    )
    celtics = Participant(
        id=CELTICS_ID,
        sport=Sport.BASKETBALL,
        name="Boston Celtics",
        kind=ParticipantKind.TEAM,
    )
    knicks = Participant(
        id=KNICKS_ID,
        sport=Sport.BASKETBALL,
        name="New York Knicks",
        kind=ParticipantKind.TEAM,
    )
    event = Event(
        id=EVENT_ID,
        sport=Sport.BASKETBALL,
        competition=competition,
        participants=(celtics, knicks),
        scheduled_start=START,
        status=EventStatus.SCHEDULED,
    )
    total = Market(
        id=TOTAL_MARKET_ID,
        event_id=EVENT_ID,
        kind=MarketKind.TOTAL_POINTS,
        period=MarketPeriod.FULL_EVENT,
        line=Decimal("215.5"),
    )
    spread = Market(
        id=SPREAD_MARKET_ID,
        event_id=EVENT_ID,
        kind=MarketKind.HANDICAP,
        period=MarketPeriod.FULL_EVENT,
        line=Decimal("-3.5"),
    )
    selections = (
        Selection(
            id=TOTAL_OVER_ID,
            market_id=TOTAL_MARKET_ID,
            kind=SelectionKind.OVER,
        ),
        Selection(
            id=TOTAL_UNDER_ID,
            market_id=TOTAL_MARKET_ID,
            kind=SelectionKind.UNDER,
        ),
        Selection(
            id=SPREAD_CELTICS_ID,
            market_id=SPREAD_MARKET_ID,
            kind=SelectionKind.PARTICIPANT,
            participant_id=CELTICS_ID,
            handicap=Decimal("-3.5"),
        ),
        Selection(
            id=SPREAD_KNICKS_ID,
            market_id=SPREAD_MARKET_ID,
            kind=SelectionKind.PARTICIPANT,
            participant_id=KNICKS_ID,
            handicap=Decimal("3.5"),
        ),
    )
    return CanonicalRegistry(
        competitions=(competition,),
        participants=(celtics, knicks),
        events=(event,),
        markets=(total, spread),
        selections=selections,
    )


def _load_the_odds_api() -> _Observation:
    adapter = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture", markets=("spreads", "totals")),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={
                "events": "events_basketball_nba_phase17_9.json",
                "odds": "odds_event_phase17_9_basketball.json",
            }
        ),
        clock=lambda: AS_OF,
    )
    competition = next(
        value
        for value in asyncio.run(adapter.discover_competitions(Sport.BASKETBALL))
        if value.external_id == "basketball_nba"
    )
    event = asyncio.run(adapter.discover_events(competition.external_id))[0]
    snapshot = asyncio.run(adapter.fetch_odds(event.external_id))
    assert snapshot is not None
    return _Observation(adapter, event, snapshot)


def _load_oddspapi() -> _Observation:
    adapter = OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture"),
        transport=OddsPapiFixtureTransport(
            fixture_overrides={
                "/tournaments": "tournaments_basketball_phase17_9.json",
                "/fixtures": "fixtures_tournament_132_phase17_9.json",
                "/markets": "markets_phase17_9_basketball.json",
                "/odds": "odds_fixture_phase17_9_basketball.json",
            }
        ),
        clock=lambda: AS_OF,
    )
    competition = next(
        value
        for value in asyncio.run(adapter.discover_competitions(Sport.BASKETBALL))
        if value.external_id == "132"
    )
    event = asyncio.run(adapter.discover_events(competition.external_id))[0]
    snapshot = asyncio.run(adapter.fetch_odds(event.external_id))
    assert snapshot is not None
    return _Observation(adapter, event, snapshot)


def _canonical_market_id(source_market: SourceMarket) -> MarketId:
    label = source_market.label.casefold()
    if "totals" in label or "over under (incl. overtime)" in label:
        assert source_market.line == Decimal("215.5")
        return TOTAL_MARKET_ID
    if "spreads" in label or "handicap (incl. overtime)" in label:
        assert source_market.line == Decimal("-3.5")
        return SPREAD_MARKET_ID
    raise AssertionError(f"unexpected Phase 17.9 market label {source_market.label!r}")


def _canonical_selection_id(
    source_market: SourceMarket,
    source_selection: SourceSelectionQuote,
) -> SelectionId:
    market_id = _canonical_market_id(source_market)
    label = source_selection.label.casefold()
    if market_id == TOTAL_MARKET_ID:
        if label == "over":
            return TOTAL_OVER_ID
        if label == "under":
            return TOTAL_UNDER_ID
    else:
        if source_selection.label in {"Boston Celtics", "1"}:
            assert source_selection.handicap == Decimal("-3.5")
            return SPREAD_CELTICS_ID
        if source_selection.label in {"New York Knicks", "2"}:
            assert source_selection.handicap == Decimal("3.5")
            return SPREAD_KNICKS_ID
    raise AssertionError(f"unexpected Phase 17.9 selection label {source_selection.label!r}")


def _hooks(observation: _Observation) -> StaticCanonicalIdHooks:
    market_ids: dict[str, MarketId] = {}
    selection_ids: dict[tuple[str, str], SelectionId] = {}
    for source_market in observation.snapshot.markets:
        market_ids[source_market.external_market_id] = _canonical_market_id(source_market)
        for source_selection in source_market.selections:
            selection_ids[
                (source_market.external_market_id, source_selection.external_selection_id)
            ] = _canonical_selection_id(source_market, source_selection)

    return StaticCanonicalIdHooks(
        event_ids={observation.event.external_id: EVENT_ID},
        market_ids=market_ids,
        selection_ids=selection_ids,
    )


def _normalize(observation: _Observation, registry: CanonicalRegistry) -> tuple[OddsQuote, ...]:
    result = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=_hooks(observation),
        event=observation.event,
        snapshot=observation.snapshot,
        registry=registry,
        as_of=AS_OF,
        freshness_window=FRESHNESS_WINDOW,
    )
    assert result.issues == ()
    return result.quotes


def test_two_real_transports_consolidate_and_evaluate_basketball_markets() -> None:
    registry = _registry()
    the_odds_api = _load_the_odds_api()
    oddspapi = _load_oddspapi()

    assert tuple(participant.name for participant in the_odds_api.event.participants) == (
        "Boston Celtics",
        "New York Knicks",
    )
    assert tuple(participant.name for participant in oddspapi.event.participants) == (
        "Boston Celtics",
        "New York Knicks",
    )

    source_quotes = _normalize(the_odds_api, registry) + _normalize(oddspapi, registry)
    assert len(source_quotes) == 16

    store = MultiSourceLiveQuoteStore(RealtimeIngestionPolicy(freshness_window=FRESHNESS_WINDOW))
    applied = store.apply(source_quotes, observed_at=AS_OF)
    assert applied.rejected_count == 0

    consolidated = store.fresh_quotes(as_of=AS_OF)
    assert len(consolidated) == 12
    assert {quote.provider_id for quote in consolidated} == {
        PINNACLE_ID,
        BET365_ID,
        BETFAIR_ID,
    }

    for market_id, expected_ids in (
        (TOTAL_MARKET_ID, (TOTAL_OVER_ID, TOTAL_UNDER_ID)),
        (SPREAD_MARKET_ID, (SPREAD_CELTICS_ID, SPREAD_KNICKS_ID)),
    ):
        pinnacle = tuple(
            quote
            for quote in consolidated
            if quote.market_id == market_id and quote.provider_id == PINNACLE_ID
        )
        assert len(pinnacle) == 2
        assert {quote.selection_id for quote in pinnacle} == set(expected_ids)

    batch = build_market_books(
        consolidated,
        registry=registry,
        as_of=AS_OF,
        freshness_window=FRESHNESS_WINDOW,
        market_ids=(TOTAL_MARKET_ID, SPREAD_MARKET_ID),
    )
    assert len(batch.books) == 2
    assert batch.diagnostics == ()

    books = {book.market.id: book for book in batch.books}
    total = books[TOTAL_MARKET_ID]
    total_selected = {outcome.selection.id: outcome.quote for outcome in total.outcomes}
    assert total_selected[TOTAL_OVER_ID].provider_id == BET365_ID
    assert total_selected[TOTAL_OVER_ID].decimal_price == Decimal("2.10")
    assert total_selected[TOTAL_UNDER_ID].provider_id == BETFAIR_ID
    assert total_selected[TOTAL_UNDER_ID].decimal_price == Decimal("2.05")

    spread = books[SPREAD_MARKET_ID]
    spread_selected = {outcome.selection.id: outcome.quote for outcome in spread.outcomes}
    assert spread_selected[SPREAD_CELTICS_ID].provider_id == BET365_ID
    assert spread_selected[SPREAD_CELTICS_ID].decimal_price == Decimal("2.10")
    assert spread_selected[SPREAD_KNICKS_ID].provider_id == BETFAIR_ID
    assert spread_selected[SPREAD_KNICKS_ID].decimal_price == Decimal("2.05")

    for index, book in enumerate((total, spread), start=1):
        evaluation = evaluate_market(book.quotes, book.expected_selection_ids)
        assert evaluation.is_arbitrage
        opportunity = build_opportunity(
            evaluation,
            opportunity_id=OpportunityId(f"opportunity:phase17-9:{index}"),
            detected_at=AS_OF,
        )
        plan = allocate_stakes(
            opportunity,
            evaluation.quotes,
            bankroll=Decimal("100"),
            stake_plan_id=StakePlanId(f"stake-plan:phase17-9:{index}"),
            created_at=AS_OF,
            rounding_policy=CurrencyRoundingPolicy(currency="EUR"),
        )
        assert plan is not None
        assert plan.guaranteed_profit > Decimal("0")
        assert plan.guaranteed_payout > plan.bankroll


def test_regulation_period_cannot_be_unlocked_by_explicit_source_mapping() -> None:
    base = _registry()
    regulation_total = Market(
        id=MarketId("market:phase17-9:regulation-total:215.5"),
        event_id=EVENT_ID,
        kind=MarketKind.TOTAL_POINTS,
        period=MarketPeriod.REGULATION,
        line=Decimal("215.5"),
    )
    registry = CanonicalRegistry(
        competitions=base.competitions,
        participants=base.participants,
        events=base.events,
        markets=base.markets + (regulation_total,),
        selections=base.selections
        + (
            Selection(
                id=SelectionId("selection:phase17-9:regulation-over"),
                market_id=regulation_total.id,
                kind=SelectionKind.OVER,
            ),
            Selection(
                id=SelectionId("selection:phase17-9:regulation-under"),
                market_id=regulation_total.id,
                kind=SelectionKind.UNDER,
            ),
        ),
    )
    observation = _load_the_odds_api()
    total_markets = tuple(
        market for market in observation.snapshot.markets if market.label.endswith(" totals")
    )
    source_market = total_markets[0]
    selections = {
        (
            source_market.external_market_id,
            selection.external_selection_id,
        ): (
            SelectionId("selection:phase17-9:regulation-over")
            if selection.label.casefold() == "over"
            else SelectionId("selection:phase17-9:regulation-under")
        )
        for selection in source_market.selections
    }
    result = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=StaticCanonicalIdHooks(
            event_ids={observation.event.external_id: EVENT_ID},
            market_ids={source_market.external_market_id: regulation_total.id},
            selection_ids=selections,
        ),
        event=observation.event,
        snapshot=OddsSnapshot(
            provider_id=observation.snapshot.provider_id,
            external_event_id=observation.snapshot.external_event_id,
            markets=(source_market,),
            ingested_at=observation.snapshot.ingested_at,
            trace_id=observation.snapshot.trace_id,
        ),
        registry=registry,
        as_of=AS_OF,
        freshness_window=FRESHNESS_WINDOW,
    )

    assert result.quotes == ()
    assert len(result.issues) == 1
    assert result.issues[0].code.value == "unsupported_market_variant"
