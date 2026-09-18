"""Phase 17.4 end-to-end regressions for football both-teams-to-score."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

from arbiscan.arbitrage import (
    CurrencyRoundingPolicy,
    allocate_stakes,
    build_opportunity,
    evaluate_market,
)
from arbiscan.domain import (
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    OddsQuote,
    OpportunityId,
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
from arbiscan.matching import (
    CanonicalRegistry,
    EventMatcher,
    EventMatchStatus,
    MatchedCanonicalIdHooks,
    ParticipantOrderPolicy,
    StaticCanonicalIdHooks,
)
from arbiscan.normalization import (
    MarketAlias,
    MarketNormalizer,
    NormalizationIssueCode,
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
from tests.integration import test_phase16_5_real_provider_semantics as phase16_5
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as TheOddsApiFixtureTransport

MARKET_ID = MarketId("market:phase17-4:football-btts")
YES_ID = SelectionId("selection:phase17-4:btts:yes")
NO_ID = SelectionId("selection:phase17-4:btts:no")
BET365_ID = ProviderId("bookmaker:the-odds-api:bet365")
BETFAIR_ID = ProviderId("bookmaker:the-odds-api:betfair")
PINNACLE_ID = ProviderId("bookmaker:the-odds-api:pinnacle")


@dataclass(frozen=True, slots=True)
class _Observation:
    adapter: ProviderAdapter
    competition: SourceCompetition
    event: SourceEvent
    snapshot: OddsSnapshot


def _registry() -> CanonicalRegistry:
    base = phase16_5._registry()
    market = Market(
        id=MARKET_ID,
        event_id=phase16_5.EVENT_ID,
        kind=MarketKind.BOTH_TEAMS_TO_SCORE,
        period=MarketPeriod.REGULATION,
    )
    yes = Selection(
        id=YES_ID,
        market_id=market.id,
        kind=SelectionKind.YES,
    )
    no = Selection(
        id=NO_ID,
        market_id=market.id,
        kind=SelectionKind.NO,
    )
    return CanonicalRegistry(
        competitions=base.competitions,
        participants=base.participants,
        events=base.events,
        markets=(*base.markets, market),
        selections=(*base.selections, yes, no),
    )


def _market_normalizer() -> MarketNormalizer:
    aliases: list[MarketAlias] = []
    for provider_id, labels in (
        (
            THE_ODDS_API_PROVIDER_ID,
            ("Pinnacle btts", "Bet365 btts"),
        ),
        (
            ODDSPAPI_PROVIDER_ID,
            (
                "pinnacle Both Teams To Score",
                "betfair Both Teams To Score",
            ),
        ),
    ):
        aliases.extend(
            MarketAlias(
                label,
                Sport.FOOTBALL,
                MarketKind.BOTH_TEAMS_TO_SCORE,
                MarketPeriod.REGULATION,
                provider_id=provider_id,
            )
            for label in labels
        )
    return MarketNormalizer(tuple(aliases))


def _load_the_odds_api() -> _Observation:
    adapter = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture", markets=("btts",)),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={
                "events": "events_soccer_epl_phase16_5.json",
                "odds": "odds_event_phase17_4_btts.json",
            }
        ),
        clock=lambda: phase16_5.AS_OF,
    )
    competition = next(
        value
        for value in asyncio.run(adapter.discover_competitions(Sport.FOOTBALL))
        if value.external_id == "soccer_epl"
    )
    event = asyncio.run(adapter.discover_events("soccer_epl"))[0]
    snapshot = asyncio.run(adapter.fetch_odds(event.external_id))
    assert snapshot is not None
    return _Observation(adapter, competition, event, snapshot)


def _load_oddspapi() -> _Observation:
    adapter = OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture"),
        transport=OddsPapiFixtureTransport(
            fixture_overrides={
                "/markets": "markets_phase17_4.json",
                "/odds": "odds_fixture_phase17_4_btts.json",
            }
        ),
        clock=lambda: phase16_5.AS_OF,
    )
    competition = next(
        value
        for value in asyncio.run(adapter.discover_competitions(Sport.FOOTBALL))
        if value.external_id == "17"
    )
    event = asyncio.run(adapter.discover_events("17"))[0]
    snapshot = asyncio.run(adapter.fetch_odds(event.external_id))
    assert snapshot is not None
    return _Observation(adapter, competition, event, snapshot)


def _selection_id(label: str) -> SelectionId:
    normalized = label.casefold()
    if normalized == "yes":
        return YES_ID
    if normalized == "no":
        return NO_ID
    raise AssertionError(f"unexpected BTTS selection label {label!r}")


def _hooks(
    observation: _Observation,
    registry: CanonicalRegistry,
) -> MatchedCanonicalIdHooks:
    prepared = prepare_event_evidence(
        provider_id=observation.adapter.provider.id,
        event=observation.event,
        competition=observation.competition,
        competition_normalizer=phase16_5._competition_normalizer(),
        participant_normalizer=phase16_5._participant_normalizer(),
        participant_kind=ParticipantKind.TEAM,
        order_policy=ParticipantOrderPolicy.ORDERED,
    )
    assert prepared.diagnostics == ()
    assert prepared.evidence is not None

    decision = EventMatcher(registry).match(prepared.evidence)
    assert decision.status is EventMatchStatus.MATCHED
    assert decision.matched_event_id == phase16_5.EVENT_ID

    normalizer = _market_normalizer()
    market_ids: dict[str, MarketId] = {}
    selection_ids: dict[tuple[str, str], SelectionId] = {}
    for source_market in observation.snapshot.markets:
        semantic = normalizer.resolve(
            source_market.label,
            sport=Sport.FOOTBALL,
            provider_id=observation.adapter.provider.id,
        )
        assert semantic.status is ResolutionStatus.RESOLVED
        assert semantic.value is not None
        assert semantic.value.kind is MarketKind.BOTH_TEAMS_TO_SCORE
        assert semantic.value.period is MarketPeriod.REGULATION
        assert semantic.value.line is None

        market_ids[source_market.external_market_id] = MARKET_ID
        for source_selection in source_market.selections:
            selection_ids[
                (source_market.external_market_id, source_selection.external_selection_id)
            ] = _selection_id(source_selection.label)

    return MatchedCanonicalIdHooks(
        base=StaticCanonicalIdHooks(
            competition_ids={
                observation.competition.external_id: phase16_5.COMPETITION_ID,
            },
            market_ids=market_ids,
            selection_ids=selection_ids,
        ),
        event_decisions={observation.event.external_id: decision},
    )


def _normalize(
    observation: _Observation,
    registry: CanonicalRegistry,
) -> tuple[tuple[OddsQuote, ...], tuple[NormalizationIssueCode, ...]]:
    result = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=_hooks(observation, registry),
        event=observation.event,
        snapshot=observation.snapshot,
        registry=registry,
        as_of=phase16_5.AS_OF,
        freshness_window=phase16_5.FRESHNESS_WINDOW,
    )
    return result.quotes, tuple(issue.code for issue in result.issues)


def test_two_real_transports_build_same_regulation_btts_arbitrage_end_to_end() -> None:
    registry = _registry()
    observations = (_load_the_odds_api(), _load_oddspapi())

    normalized: list[OddsQuote] = []
    for observation in observations:
        quotes, issues = _normalize(observation, registry)
        assert issues == ()
        assert quotes
        assert {quote.market_id for quote in quotes} == {MARKET_ID}
        normalized.extend(quotes)

    assert len(normalized) == 8
    store = MultiSourceLiveQuoteStore(
        RealtimeIngestionPolicy(freshness_window=phase16_5.FRESHNESS_WINDOW)
    )
    applied = store.apply(tuple(normalized), observed_at=phase16_5.AS_OF)
    assert applied.rejected_count == 0

    consolidated = store.fresh_quotes(as_of=phase16_5.AS_OF)
    assert len(consolidated) == 6
    assert {quote.provider_id for quote in consolidated} == {
        PINNACLE_ID,
        BET365_ID,
        BETFAIR_ID,
    }

    batch = build_market_books(
        consolidated,
        registry=registry,
        as_of=phase16_5.AS_OF,
        freshness_window=phase16_5.FRESHNESS_WINDOW,
        market_ids=(MARKET_ID,),
    )
    assert len(batch.books) == 1
    book = batch.books[0]
    assert set(book.expected_selection_ids) == {YES_ID, NO_ID}

    selected = {outcome.selection.id: outcome.quote for outcome in book.outcomes}
    assert selected[YES_ID].provider_id == BET365_ID
    assert selected[YES_ID].decimal_price == Decimal("2.10")
    assert selected[YES_ID].transport_provider_id == THE_ODDS_API_PROVIDER_ID
    assert selected[NO_ID].provider_id == BETFAIR_ID
    assert selected[NO_ID].decimal_price == Decimal("2.05")
    assert selected[NO_ID].transport_provider_id == ODDSPAPI_PROVIDER_ID

    evaluation = evaluate_market(book.quotes, book.expected_selection_ids)
    assert evaluation.is_arbitrage
    assert evaluation.implied_probability_sum < Decimal("1")

    opportunity = build_opportunity(
        evaluation,
        opportunity_id=OpportunityId("opportunity:phase17-4:football-btts"),
        detected_at=phase16_5.AS_OF,
    )
    plan = allocate_stakes(
        opportunity,
        evaluation.quotes,
        bankroll=Decimal("100"),
        stake_plan_id=StakePlanId("stake-plan:phase17-4:football-btts"),
        created_at=phase16_5.AS_OF,
        rounding_policy=CurrencyRoundingPolicy(currency="EUR"),
    )

    assert plan is not None
    assert plan.guaranteed_profit > Decimal("0")
    assert plan.guaranteed_payout > plan.bankroll
