"""Phase 16.5 tennis winner semantics across both real provider schemas."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
    OddsQuote,
    Participant,
    ParticipantId,
    ParticipantKind,
    ProviderEventReference,
    ProviderId,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
)
from arbiscan.matching import (
    CanonicalRegistry,
    EventMatchDecision,
    EventMatcher,
    EventMatchStatus,
    MatchedCanonicalIdHooks,
    ParticipantOrderPolicy,
    StaticCanonicalIdHooks,
)
from arbiscan.normalization import (
    CompetitionAlias,
    CompetitionNormalizer,
    MarketAlias,
    MarketNormalizer,
    ParticipantAlias,
    ParticipantNormalizer,
    ResolutionStatus,
    normalize_source_snapshot,
    prepare_event_evidence,
)
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.models import OddsSnapshot, SourceCompetition, SourceEvent
from arbiscan.providers.oddspapi import ODDSPAPI_PROVIDER_ID, OddsPapiConfig, OddsPapiProvider
from arbiscan.providers.the_odds_api import (
    THE_ODDS_API_PROVIDER_ID,
    TheOddsApiConfig,
    TheOddsApiProvider,
)
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as TheOddsApiFixtureTransport

AS_OF = datetime(2026, 9, 18, 14, 59, tzinfo=UTC)
FRESHNESS_WINDOW = timedelta(minutes=2)

COMPETITION_ID = CompetitionId("competition:phase16-5:us-open")
EVENT_ID = EventId("event:phase16-5:sinner-alcaraz")
MARKET_ID = MarketId("market:phase16-5:tennis-match-winner")
SINNER_ID = ParticipantId("participant:phase16-5:jannik-sinner")
ALCARAZ_ID = ParticipantId("participant:phase16-5:carlos-alcaraz")
SINNER_SELECTION_ID = SelectionId("selection:phase16-5:jannik-sinner")
ALCARAZ_SELECTION_ID = SelectionId("selection:phase16-5:carlos-alcaraz")

THE_ODDS_EVENT_ID = "us-open-sinner-alcaraz-20260918"
ODDSPAPI_EVENT_ID = "id1000001761301777"
PINNACLE_ID = ProviderId("bookmaker:the-odds-api:pinnacle")


@dataclass(frozen=True, slots=True)
class _Observation:
    adapter: ProviderAdapter
    competition: SourceCompetition
    event: SourceEvent
    snapshot: OddsSnapshot


def _registry() -> CanonicalRegistry:
    competition = Competition(
        id=COMPETITION_ID,
        sport=Sport.TENNIS,
        name="US Open",
        region="USA",
    )
    sinner = Participant(
        id=SINNER_ID,
        sport=Sport.TENNIS,
        name="Jannik Sinner",
        kind=ParticipantKind.INDIVIDUAL,
    )
    alcaraz = Participant(
        id=ALCARAZ_ID,
        sport=Sport.TENNIS,
        name="Carlos Alcaraz",
        kind=ParticipantKind.INDIVIDUAL,
    )
    event = Event(
        id=EVENT_ID,
        sport=Sport.TENNIS,
        competition=competition,
        participants=(sinner, alcaraz),
        scheduled_start=datetime(2026, 9, 18, 15, 0, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
        provider_references=(
            ProviderEventReference(
                provider_id=THE_ODDS_API_PROVIDER_ID,
                external_event_id=THE_ODDS_EVENT_ID,
            ),
            ProviderEventReference(
                provider_id=ODDSPAPI_PROVIDER_ID,
                external_event_id=ODDSPAPI_EVENT_ID,
            ),
        ),
    )
    market = Market(
        id=MARKET_ID,
        event_id=EVENT_ID,
        kind=MarketKind.MATCH_WINNER_2_WAY,
        period=MarketPeriod.FULL_EVENT,
    )
    selections = (
        Selection(
            id=SINNER_SELECTION_ID,
            market_id=MARKET_ID,
            kind=SelectionKind.PARTICIPANT,
            participant_id=SINNER_ID,
        ),
        Selection(
            id=ALCARAZ_SELECTION_ID,
            market_id=MARKET_ID,
            kind=SelectionKind.PARTICIPANT,
            participant_id=ALCARAZ_ID,
        ),
    )
    return CanonicalRegistry(
        competitions=(competition,),
        participants=(sinner, alcaraz),
        events=(event,),
        markets=(market,),
        selections=selections,
    )


def _competition_normalizer() -> CompetitionNormalizer:
    return CompetitionNormalizer(
        (
            CompetitionAlias(
                "ATP US Open",
                COMPETITION_ID,
                Sport.TENNIS,
                provider_id=THE_ODDS_API_PROVIDER_ID,
                region="Tennis",
            ),
            CompetitionAlias(
                "US Open",
                COMPETITION_ID,
                Sport.TENNIS,
                provider_id=ODDSPAPI_PROVIDER_ID,
                region="USA",
            ),
        )
    )


def _participant_normalizer() -> ParticipantNormalizer:
    entries: list[ParticipantAlias] = []
    for provider_id in (THE_ODDS_API_PROVIDER_ID, ODDSPAPI_PROVIDER_ID):
        entries.extend(
            (
                ParticipantAlias(
                    "Jannik Sinner",
                    SINNER_ID,
                    Sport.TENNIS,
                    ParticipantKind.INDIVIDUAL,
                    provider_id=provider_id,
                    competition_id=COMPETITION_ID,
                ),
                ParticipantAlias(
                    "Carlos Alcaraz",
                    ALCARAZ_ID,
                    Sport.TENNIS,
                    ParticipantKind.INDIVIDUAL,
                    provider_id=provider_id,
                    competition_id=COMPETITION_ID,
                ),
            )
        )
    return ParticipantNormalizer(tuple(entries))


def _market_normalizer() -> MarketNormalizer:
    return MarketNormalizer(
        (
            MarketAlias(
                "Pinnacle h2h",
                Sport.TENNIS,
                MarketKind.MATCH_WINNER_2_WAY,
                MarketPeriod.FULL_EVENT,
                provider_id=THE_ODDS_API_PROVIDER_ID,
            ),
            MarketAlias(
                "pinnacle Match Winner",
                Sport.TENNIS,
                MarketKind.MATCH_WINNER_2_WAY,
                MarketPeriod.FULL_EVENT,
                provider_id=ODDSPAPI_PROVIDER_ID,
            ),
        )
    )


def _load_observations() -> tuple[_Observation, _Observation]:
    the_odds_api = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture"),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={
                "events": "events_tennis_atp_us_open_phase16_5.json",
                "odds": "odds_event_tennis_phase16_5.json",
            }
        ),
        clock=lambda: AS_OF,
    )
    the_odds_competition = next(
        value
        for value in asyncio.run(the_odds_api.discover_competitions(Sport.TENNIS))
        if value.external_id == "tennis_atp_us_open"
    )
    the_odds_event = asyncio.run(the_odds_api.discover_events("tennis_atp_us_open"))[0]
    the_odds_snapshot = asyncio.run(the_odds_api.fetch_odds(the_odds_event.external_id))
    assert the_odds_snapshot is not None

    oddspapi = OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture"),
        transport=OddsPapiFixtureTransport(
            fixture_overrides={
                "/tournaments": "tournaments_tennis_phase16_5.json",
                "/fixtures": "fixtures_tournament_77_phase16_5.json",
                "/odds": "odds_tennis_phase16_5.json",
            }
        ),
        clock=lambda: AS_OF,
    )
    oddspapi_competition = next(
        value
        for value in asyncio.run(oddspapi.discover_competitions(Sport.TENNIS))
        if value.external_id == "77"
    )
    oddspapi_event = asyncio.run(oddspapi.discover_events("77"))[0]
    oddspapi_snapshot = asyncio.run(oddspapi.fetch_odds(oddspapi_event.external_id))
    assert oddspapi_snapshot is not None

    return (
        _Observation(
            adapter=the_odds_api,
            competition=the_odds_competition,
            event=the_odds_event,
            snapshot=the_odds_snapshot,
        ),
        _Observation(
            adapter=oddspapi,
            competition=oddspapi_competition,
            event=oddspapi_event,
            snapshot=oddspapi_snapshot,
        ),
    )


def _selection_id(provider_id: ProviderId, label: str) -> SelectionId | None:
    if provider_id == THE_ODDS_API_PROVIDER_ID:
        return {
            "Jannik Sinner": SINNER_SELECTION_ID,
            "Carlos Alcaraz": ALCARAZ_SELECTION_ID,
        }.get(label)
    if provider_id == ODDSPAPI_PROVIDER_ID:
        return {
            "1": ALCARAZ_SELECTION_ID,
            "2": SINNER_SELECTION_ID,
        }.get(label)
    return None


def _validated_hooks(
    observation: _Observation,
    registry: CanonicalRegistry,
) -> tuple[MatchedCanonicalIdHooks, EventMatchDecision]:
    prepared = prepare_event_evidence(
        provider_id=observation.adapter.provider.id,
        event=observation.event,
        competition=observation.competition,
        competition_normalizer=_competition_normalizer(),
        participant_normalizer=_participant_normalizer(),
        participant_kind=ParticipantKind.INDIVIDUAL,
        order_policy=ParticipantOrderPolicy.UNORDERED,
    )
    assert prepared.diagnostics == ()
    assert prepared.evidence is not None

    decision = EventMatcher(registry).match(prepared.evidence)
    assert decision.status is EventMatchStatus.MATCHED
    assert decision.matched_event_id == EVENT_ID

    market_ids: dict[str, MarketId] = {}
    selection_ids: dict[tuple[str, str], SelectionId] = {}
    market_normalizer = _market_normalizer()
    for source_market in observation.snapshot.markets:
        semantic = market_normalizer.resolve(
            source_market.label,
            sport=observation.event.sport,
            provider_id=observation.adapter.provider.id,
        )
        assert semantic.status is ResolutionStatus.RESOLVED
        assert semantic.value is not None
        assert semantic.value.kind is MarketKind.MATCH_WINNER_2_WAY
        assert semantic.value.period is MarketPeriod.FULL_EVENT
        market_ids[source_market.external_market_id] = MARKET_ID

        for source_selection in source_market.selections:
            selection_id = _selection_id(
                observation.adapter.provider.id,
                source_selection.label,
            )
            assert selection_id is not None
            selection_ids[
                (source_market.external_market_id, source_selection.external_selection_id)
            ] = selection_id

    base = StaticCanonicalIdHooks(
        competition_ids={observation.competition.external_id: COMPETITION_ID},
        market_ids=market_ids,
        selection_ids=selection_ids,
    )
    return (
        MatchedCanonicalIdHooks(
            base=base,
            event_decisions={observation.event.external_id: decision},
        ),
        decision,
    )


def test_tennis_winner_semantics_match_despite_opposite_provider_participant_order() -> None:
    registry = _registry()
    the_odds, oddspapi = _load_observations()
    assert tuple(value.name for value in the_odds.event.participants) == (
        "Jannik Sinner",
        "Carlos Alcaraz",
    )
    assert tuple(value.name for value in oddspapi.event.participants) == (
        "Carlos Alcaraz",
        "Jannik Sinner",
    )

    normalized_by_provider: dict[ProviderId, tuple[OddsQuote, ...]] = {}
    for observation in (the_odds, oddspapi):
        hooks, decision = _validated_hooks(observation, registry)
        assert decision.confidence_bps is not None
        normalized = normalize_source_snapshot(
            provider=observation.adapter.provider,
            hooks=hooks,
            event=observation.event,
            snapshot=observation.snapshot,
            registry=registry,
            as_of=AS_OF,
            freshness_window=FRESHNESS_WINDOW,
        )
        assert normalized.issues == ()
        assert len(normalized.quotes) == 2
        normalized_by_provider[observation.adapter.provider.id] = normalized.quotes

    expected_selections = {SINNER_SELECTION_ID, ALCARAZ_SELECTION_ID}
    for provider_id, quotes in normalized_by_provider.items():
        assert {quote.event_id for quote in quotes} == {EVENT_ID}
        assert {quote.market_id for quote in quotes} == {MARKET_ID}
        assert {quote.selection_id for quote in quotes} == expected_selections
        assert {quote.provider_id for quote in quotes} == {PINNACLE_ID}
        assert {quote.transport_provider_id for quote in quotes} == {provider_id}
