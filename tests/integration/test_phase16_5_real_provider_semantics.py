"""Phase 16.5 validation across the two real provider adapter schemas."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
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
    EventMatchReason,
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
    NormalizationIssueCode,
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

CANONICAL_START = datetime(2026, 9, 17, 18, 0, tzinfo=UTC)
AS_OF = datetime(2026, 9, 17, 10, 21, tzinfo=UTC)
FRESHNESS_WINDOW = timedelta(minutes=2)

COMPETITION_ID = CompetitionId("competition:phase16-5:epl")
EVENT_ID = EventId("event:phase16-5:liverpool-manchester-united")
MARKET_ID = MarketId("market:phase16-5:football-1x2")
LIVERPOOL_ID = ParticipantId("participant:phase16-5:liverpool")
MANCHESTER_UNITED_ID = ParticipantId("participant:phase16-5:manchester-united")
HOME_SELECTION_ID = SelectionId("selection:phase16-5:liverpool")
DRAW_SELECTION_ID = SelectionId("selection:phase16-5:draw")
AWAY_SELECTION_ID = SelectionId("selection:phase16-5:manchester-united")

THE_ODDS_EVENT_ID = "epl-liverpool-manchester-united-20260917"
ODDSPAPI_EVENT_ID = "id1000001761301153"
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
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
    )
    liverpool = Participant(
        id=LIVERPOOL_ID,
        sport=Sport.FOOTBALL,
        name="Liverpool",
        kind=ParticipantKind.TEAM,
    )
    manchester_united = Participant(
        id=MANCHESTER_UNITED_ID,
        sport=Sport.FOOTBALL,
        name="Manchester United",
        kind=ParticipantKind.TEAM,
    )
    event = Event(
        id=EVENT_ID,
        sport=Sport.FOOTBALL,
        competition=competition,
        participants=(liverpool, manchester_united),
        scheduled_start=CANONICAL_START,
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
        kind=MarketKind.MATCH_WINNER_3_WAY,
        period=MarketPeriod.REGULATION,
    )
    selections = (
        Selection(
            id=HOME_SELECTION_ID,
            market_id=MARKET_ID,
            kind=SelectionKind.PARTICIPANT,
            participant_id=LIVERPOOL_ID,
        ),
        Selection(
            id=DRAW_SELECTION_ID,
            market_id=MARKET_ID,
            kind=SelectionKind.DRAW,
        ),
        Selection(
            id=AWAY_SELECTION_ID,
            market_id=MARKET_ID,
            kind=SelectionKind.PARTICIPANT,
            participant_id=MANCHESTER_UNITED_ID,
        ),
    )
    return CanonicalRegistry(
        competitions=(competition,),
        participants=(liverpool, manchester_united),
        events=(event,),
        markets=(market,),
        selections=selections,
    )


def _competition_normalizer() -> CompetitionNormalizer:
    return CompetitionNormalizer(
        (
            CompetitionAlias(
                "EPL",
                COMPETITION_ID,
                Sport.FOOTBALL,
                provider_id=THE_ODDS_API_PROVIDER_ID,
                region="Soccer",
            ),
            CompetitionAlias(
                "Premier League",
                COMPETITION_ID,
                Sport.FOOTBALL,
                provider_id=ODDSPAPI_PROVIDER_ID,
                region="England",
            ),
        )
    )


def _participant_normalizer() -> ParticipantNormalizer:
    entries: list[ParticipantAlias] = []
    for provider_id in (THE_ODDS_API_PROVIDER_ID, ODDSPAPI_PROVIDER_ID):
        entries.extend(
            (
                ParticipantAlias(
                    "Liverpool FC",
                    LIVERPOOL_ID,
                    Sport.FOOTBALL,
                    ParticipantKind.TEAM,
                    provider_id=provider_id,
                    competition_id=COMPETITION_ID,
                ),
                ParticipantAlias(
                    "Manchester United",
                    MANCHESTER_UNITED_ID,
                    Sport.FOOTBALL,
                    ParticipantKind.TEAM,
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
                Sport.FOOTBALL,
                MarketKind.MATCH_WINNER_3_WAY,
                MarketPeriod.REGULATION,
                provider_id=THE_ODDS_API_PROVIDER_ID,
            ),
            MarketAlias(
                "pinnacle Full Time Result",
                Sport.FOOTBALL,
                MarketKind.MATCH_WINNER_3_WAY,
                MarketPeriod.REGULATION,
                provider_id=ODDSPAPI_PROVIDER_ID,
            ),
        )
    )


def _load_observations() -> tuple[_Observation, _Observation]:
    the_odds_api = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture"),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={
                "events": "events_soccer_epl_phase16_5.json",
                "odds": "odds_event_phase16_5.json",
            }
        ),
        clock=lambda: AS_OF,
    )
    the_odds_competition = next(
        value
        for value in asyncio.run(the_odds_api.discover_competitions(Sport.FOOTBALL))
        if value.external_id == "soccer_epl"
    )
    the_odds_event = asyncio.run(the_odds_api.discover_events("soccer_epl"))[0]
    the_odds_snapshot = asyncio.run(the_odds_api.fetch_odds(the_odds_event.external_id))
    assert the_odds_snapshot is not None

    oddspapi = OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture"),
        transport=OddsPapiFixtureTransport(),
        clock=lambda: AS_OF,
    )
    oddspapi_competition = next(
        value
        for value in asyncio.run(oddspapi.discover_competitions(Sport.FOOTBALL))
        if value.external_id == "17"
    )
    oddspapi_event = asyncio.run(oddspapi.discover_events("17"))[0]
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
            "Liverpool FC": HOME_SELECTION_ID,
            "Draw": DRAW_SELECTION_ID,
            "Manchester United": AWAY_SELECTION_ID,
        }.get(label)
    if provider_id == ODDSPAPI_PROVIDER_ID:
        return {
            "1": HOME_SELECTION_ID,
            "X": DRAW_SELECTION_ID,
            "2": AWAY_SELECTION_ID,
        }.get(label)
    return None


def _validated_hooks(
    observation: _Observation,
    registry: CanonicalRegistry,
    *,
    omit_selection_label: str | None = None,
) -> tuple[MatchedCanonicalIdHooks, EventMatchDecision]:
    prepared = prepare_event_evidence(
        provider_id=observation.adapter.provider.id,
        event=observation.event,
        competition=observation.competition,
        competition_normalizer=_competition_normalizer(),
        participant_normalizer=_participant_normalizer(),
        participant_kind=ParticipantKind.TEAM,
        order_policy=ParticipantOrderPolicy.ORDERED,
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
        assert semantic.value.kind is MarketKind.MATCH_WINNER_3_WAY
        assert semantic.value.period is MarketPeriod.REGULATION
        market_ids[source_market.external_market_id] = MARKET_ID

        for source_selection in source_market.selections:
            if source_selection.label == omit_selection_label:
                continue
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


def test_two_real_source_schemas_match_and_normalize_to_the_same_mvp_event() -> None:
    registry = _registry()
    observations = _load_observations()
    normalized_by_provider = {}

    for observation in observations:
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
        assert len(normalized.quotes) == 3
        normalized_by_provider[observation.adapter.provider.id] = normalized.quotes

    expected_selections = {
        HOME_SELECTION_ID,
        DRAW_SELECTION_ID,
        AWAY_SELECTION_ID,
    }
    quote_ids: set[str] = set()
    for provider_id, quotes in normalized_by_provider.items():
        assert {quote.event_id for quote in quotes} == {EVENT_ID}
        assert {quote.market_id for quote in quotes} == {MARKET_ID}
        assert {quote.selection_id for quote in quotes} == expected_selections
        assert {quote.provider_id for quote in quotes} == {PINNACLE_ID}
        assert {quote.transport_provider_id for quote in quotes} == {provider_id}
        assert not quote_ids.intersection(quote.id.value for quote in quotes)
        quote_ids.update(quote.id.value for quote in quotes)

    the_odds_quotes = normalized_by_provider[THE_ODDS_API_PROVIDER_ID]
    assert {quote.source_timestamp for quote in the_odds_quotes} == {
        datetime(2026, 9, 17, 10, 20, 4, tzinfo=UTC)
    }
    oddspapi_quotes = normalized_by_provider[ODDSPAPI_PROVIDER_ID]
    assert {quote.source_timestamp for quote in oddspapi_quotes} == {
        datetime(2026, 9, 17, 10, 20, 0, tzinfo=UTC),
        datetime(2026, 9, 17, 10, 20, 2, tzinfo=UTC),
        datetime(2026, 9, 17, 10, 20, 3, tzinfo=UTC),
    }


def test_ordered_football_participants_reject_reversed_source_identity() -> None:
    registry = _registry()
    observation = _load_observations()[0]
    reversed_event = replace(
        observation.event,
        participants=tuple(reversed(observation.event.participants)),
    )
    prepared = prepare_event_evidence(
        provider_id=observation.adapter.provider.id,
        event=reversed_event,
        competition=observation.competition,
        competition_normalizer=_competition_normalizer(),
        participant_normalizer=_participant_normalizer(),
        participant_kind=ParticipantKind.TEAM,
        order_policy=ParticipantOrderPolicy.ORDERED,
    )
    assert prepared.evidence is not None

    decision = EventMatcher(registry).match(prepared.evidence)

    assert decision.status is EventMatchStatus.REJECTED
    assert any(
        diagnostic.reason is EventMatchReason.PARTICIPANT_ORDER_MISMATCH
        for diagnostic in decision.diagnostics
    )


def test_verified_match_is_required_for_real_source_reschedule() -> None:
    registry = _registry()
    observation = _load_observations()[0]
    assert observation.event.scheduled_start != CANONICAL_START
    matched_hooks, _decision = _validated_hooks(observation, registry)

    matched = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=matched_hooks,
        event=observation.event,
        snapshot=observation.snapshot,
        registry=registry,
        as_of=AS_OF,
        freshness_window=FRESHNESS_WINDOW,
    )
    assert matched.issues == ()
    assert matched.quotes

    base = matched_hooks.base
    assert isinstance(base, StaticCanonicalIdHooks)
    static_hooks = StaticCanonicalIdHooks(
        competition_ids=base.competition_ids,
        event_ids={observation.event.external_id: EVENT_ID},
        market_ids=base.market_ids,
        selection_ids=base.selection_ids,
    )
    unverified = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=static_hooks,
        event=observation.event,
        snapshot=observation.snapshot,
        registry=registry,
        as_of=AS_OF,
        freshness_window=FRESHNESS_WINDOW,
    )

    assert unverified.quotes == ()
    assert tuple(issue.code for issue in unverified.issues) == (
        NormalizationIssueCode.IDENTITY_MISMATCH,
    )


def test_unknown_selection_and_status_semantics_fail_closed() -> None:
    registry = _registry()
    oddspapi = _load_observations()[1]
    hooks, _decision = _validated_hooks(
        oddspapi,
        registry,
        omit_selection_label="X",
    )

    missing_selection = normalize_source_snapshot(
        provider=oddspapi.adapter.provider,
        hooks=hooks,
        event=oddspapi.event,
        snapshot=oddspapi.snapshot,
        registry=registry,
        as_of=AS_OF,
        freshness_window=FRESHNESS_WINDOW,
    )
    assert len(missing_selection.quotes) == 2
    assert tuple(issue.code for issue in missing_selection.issues) == (
        NormalizationIssueCode.UNMAPPED_SELECTION,
    )

    complete_hooks, _decision = _validated_hooks(oddspapi, registry)
    unknown_market = replace(oddspapi.snapshot.markets[0], source_status="provider-unknown")
    unknown_snapshot = replace(oddspapi.snapshot, markets=(unknown_market,))
    unknown_status = normalize_source_snapshot(
        provider=oddspapi.adapter.provider,
        hooks=complete_hooks,
        event=oddspapi.event,
        snapshot=unknown_snapshot,
        registry=registry,
        as_of=AS_OF,
        freshness_window=FRESHNESS_WINDOW,
    )
    assert unknown_status.quotes == ()
    assert tuple(issue.code for issue in unknown_status.issues) == (
        NormalizationIssueCode.INACTIVE_MARKET,
    )


def test_real_source_freshness_timestamp_controls_quote_eligibility() -> None:
    registry = _registry()
    observation = _load_observations()[0]
    hooks, _decision = _validated_hooks(observation, registry)

    stale = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=hooks,
        event=observation.event,
        snapshot=observation.snapshot,
        registry=registry,
        as_of=AS_OF + timedelta(minutes=10),
        freshness_window=FRESHNESS_WINDOW,
    )

    assert stale.quotes == ()
    assert tuple(issue.code for issue in stale.issues) == (
        NormalizationIssueCode.STALE_SNAPSHOT,
    )
