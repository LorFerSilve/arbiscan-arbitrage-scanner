"""Phase 17.6 indexed tennis set-winner integration regressions."""

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
from tests.integration import test_phase16_5_tennis_semantics as phase16_tennis
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixtureTransport

SET1_MARKET_ID = MarketId("market:phase17-6:tennis:set:1:winner")
SET2_MARKET_ID = MarketId("market:phase17-6:tennis:set:2:winner")
SET1_SINNER_ID = SelectionId("selection:phase17-6:set1:sinner")
SET1_ALCARAZ_ID = SelectionId("selection:phase17-6:set1:alcaraz")
SET2_SINNER_ID = SelectionId("selection:phase17-6:set2:sinner")
SET2_ALCARAZ_ID = SelectionId("selection:phase17-6:set2:alcaraz")

PINNACLE_ID = ProviderId("bookmaker:the-odds-api:pinnacle")
BETFAIR_ID = ProviderId("bookmaker:the-odds-api:betfair")


@dataclass(frozen=True, slots=True)
class _Observation:
    adapter: ProviderAdapter
    competition: SourceCompetition
    event: SourceEvent
    snapshot: OddsSnapshot


def _market_id(period_index: int) -> MarketId:
    if period_index == 1:
        return SET1_MARKET_ID
    if period_index == 2:
        return SET2_MARKET_ID
    raise AssertionError(f"unexpected set index {period_index}")


def _selection_id(period_index: int, source_label: str) -> SelectionId:
    if period_index == 1:
        return {
            "1": SET1_ALCARAZ_ID,
            "2": SET1_SINNER_ID,
        }[source_label]
    if period_index == 2:
        return {
            "1": SET2_ALCARAZ_ID,
            "2": SET2_SINNER_ID,
        }[source_label]
    raise AssertionError(f"unexpected set index {period_index}")


def _registry() -> CanonicalRegistry:
    base = phase16_tennis._registry()
    set1 = Market(
        id=SET1_MARKET_ID,
        event_id=phase16_tennis.EVENT_ID,
        kind=MarketKind.SET_WINNER,
        period=MarketPeriod.SET,
        period_index=1,
    )
    set2 = Market(
        id=SET2_MARKET_ID,
        event_id=phase16_tennis.EVENT_ID,
        kind=MarketKind.SET_WINNER,
        period=MarketPeriod.SET,
        period_index=2,
    )
    selections = (
        Selection(
            id=SET1_SINNER_ID,
            market_id=set1.id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=phase16_tennis.SINNER_ID,
        ),
        Selection(
            id=SET1_ALCARAZ_ID,
            market_id=set1.id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=phase16_tennis.ALCARAZ_ID,
        ),
        Selection(
            id=SET2_SINNER_ID,
            market_id=set2.id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=phase16_tennis.SINNER_ID,
        ),
        Selection(
            id=SET2_ALCARAZ_ID,
            market_id=set2.id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=phase16_tennis.ALCARAZ_ID,
        ),
    )
    return CanonicalRegistry(
        competitions=base.competitions,
        participants=base.participants,
        events=base.events,
        markets=(*base.markets, set1, set2),
        selections=(*base.selections, *selections),
    )


def _market_normalizer() -> MarketNormalizer:
    aliases = tuple(
        MarketAlias(
            f"{bookmaker} {market_name}",
            Sport.TENNIS,
            MarketKind.SET_WINNER,
            MarketPeriod.SET,
            provider_id=ODDSPAPI_PROVIDER_ID,
            requires_period_index=True,
        )
        for bookmaker in ("pinnacle", "betfair")
        for market_name in ("First Set Winner", "Second Set Winner")
    )
    return MarketNormalizer(aliases)


def _load_oddspapi() -> _Observation:
    adapter = OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture"),
        transport=OddsPapiFixtureTransport(
            fixture_overrides={
                "/tournaments": "tournaments_tennis_phase16_5.json",
                "/fixtures": "fixtures_tournament_77_phase16_5.json",
                "/markets": "markets_phase17_6_tennis_sets.json",
                "/odds": "odds_fixture_phase17_6_tennis_sets.json",
            }
        ),
        clock=lambda: phase16_tennis.AS_OF,
    )
    competition = next(
        value
        for value in asyncio.run(adapter.discover_competitions(Sport.TENNIS))
        if value.external_id == "77"
    )
    event = asyncio.run(adapter.discover_events("77"))[0]
    snapshot = asyncio.run(adapter.fetch_odds(event.external_id))
    assert snapshot is not None
    return _Observation(adapter, competition, event, snapshot)


def _hooks(
    observation: _Observation,
    registry: CanonicalRegistry,
) -> MatchedCanonicalIdHooks:
    prepared = prepare_event_evidence(
        provider_id=observation.adapter.provider.id,
        event=observation.event,
        competition=observation.competition,
        competition_normalizer=phase16_tennis._competition_normalizer(),
        participant_normalizer=phase16_tennis._participant_normalizer(),
        participant_kind=ParticipantKind.INDIVIDUAL,
        order_policy=ParticipantOrderPolicy.UNORDERED,
    )
    assert prepared.diagnostics == ()
    assert prepared.evidence is not None

    decision = EventMatcher(registry).match(prepared.evidence)
    assert decision.status is EventMatchStatus.MATCHED
    assert decision.matched_event_id == phase16_tennis.EVENT_ID

    normalizer = _market_normalizer()
    market_ids: dict[str, MarketId] = {}
    selection_ids: dict[tuple[str, str], SelectionId] = {}
    for source_market in observation.snapshot.markets:
        assert source_market.period_index in {1, 2}
        semantic = normalizer.resolve(
            source_market.label,
            sport=Sport.TENNIS,
            provider_id=ODDSPAPI_PROVIDER_ID,
            period_index=source_market.period_index,
        )
        assert semantic.status is ResolutionStatus.RESOLVED
        assert semantic.value is not None
        assert semantic.value.kind is MarketKind.SET_WINNER
        assert semantic.value.period is MarketPeriod.SET
        assert semantic.value.period_index == source_market.period_index

        market_ids[source_market.external_market_id] = _market_id(source_market.period_index)
        for source_selection in source_market.selections:
            selection_ids[
                (source_market.external_market_id, source_selection.external_selection_id)
            ] = _selection_id(source_market.period_index, source_selection.label)

    return MatchedCanonicalIdHooks(
        base=StaticCanonicalIdHooks(
            competition_ids={
                observation.competition.external_id: phase16_tennis.COMPETITION_ID,
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
        as_of=phase16_tennis.AS_OF,
        freshness_window=phase16_tennis.FRESHNESS_WINDOW,
    )
    return result.quotes, tuple(issue.code for issue in result.issues)


def test_indexed_set_winners_never_cross_compare_and_set_one_arbitrage_is_executable() -> None:
    registry = _registry()
    observation = _load_oddspapi()

    quotes, issues = _normalize(observation, registry)

    assert issues == ()
    assert len(quotes) == 8
    assert {quote.market_id for quote in quotes} == {SET1_MARKET_ID, SET2_MARKET_ID}
    assert {quote.provider_id for quote in quotes} == {PINNACLE_ID, BETFAIR_ID}
    assert {quote.transport_provider_id for quote in quotes} == {ODDSPAPI_PROVIDER_ID}

    batch = build_market_books(
        quotes,
        registry=registry,
        as_of=phase16_tennis.AS_OF,
        freshness_window=phase16_tennis.FRESHNESS_WINDOW,
        market_ids=(SET1_MARKET_ID, SET2_MARKET_ID),
    )
    assert len(batch.books) == 2
    books = {book.market.id: book for book in batch.books}
    assert set(books) == {SET1_MARKET_ID, SET2_MARKET_ID}

    set1 = books[SET1_MARKET_ID]
    selected = {outcome.selection.id: outcome.quote for outcome in set1.outcomes}
    assert selected[SET1_ALCARAZ_ID].provider_id == BETFAIR_ID
    assert selected[SET1_ALCARAZ_ID].decimal_price == Decimal("2.10")
    assert selected[SET1_SINNER_ID].provider_id == PINNACLE_ID
    assert selected[SET1_SINNER_ID].decimal_price == Decimal("2.05")

    set1_evaluation = evaluate_market(set1.quotes, set1.expected_selection_ids)
    assert set1_evaluation.is_arbitrage
    opportunity = build_opportunity(
        set1_evaluation,
        opportunity_id=OpportunityId("opportunity:phase17-6:tennis:set1"),
        detected_at=phase16_tennis.AS_OF,
    )
    plan = allocate_stakes(
        opportunity,
        set1_evaluation.quotes,
        bankroll=Decimal("100"),
        stake_plan_id=StakePlanId("stake-plan:phase17-6:tennis:set1"),
        created_at=phase16_tennis.AS_OF,
        rounding_policy=CurrencyRoundingPolicy(currency="EUR"),
    )
    assert plan is not None
    assert plan.guaranteed_profit > Decimal("0")

    set2 = books[SET2_MARKET_ID]
    set2_evaluation = evaluate_market(set2.quotes, set2.expected_selection_ids)
    assert not set2_evaluation.is_arbitrage


def test_structured_period_index_mismatch_fails_before_quote_creation() -> None:
    registry = _registry()
    observation = _load_oddspapi()
    hooks = _hooks(observation, registry)

    source_set1_market_ids = {
        market.external_market_id
        for market in observation.snapshot.markets
        if market.period_index == 1
    }
    remapped = dict(hooks.base.market_ids)
    for source_market_id in source_set1_market_ids:
        remapped[source_market_id] = SET2_MARKET_ID

    mismatched_hooks = MatchedCanonicalIdHooks(
        base=StaticCanonicalIdHooks(
            competition_ids=hooks.base.competition_ids,
            market_ids=remapped,
            selection_ids=hooks.base.selection_ids,
        ),
        event_decisions=hooks.event_decisions,
    )
    result = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=mismatched_hooks,
        event=observation.event,
        snapshot=observation.snapshot,
        registry=registry,
        as_of=phase16_tennis.AS_OF,
        freshness_window=phase16_tennis.FRESHNESS_WINDOW,
    )

    set1_issues = [
        issue for issue in result.issues if issue.external_market_id in source_set1_market_ids
    ]
    assert set1_issues
    assert {issue.code for issue in set1_issues} == {
        NormalizationIssueCode.MARKET_PARAMETER_MISMATCH
    }
    assert all(
        quote.market_id != SET2_MARKET_ID or quote.source_market_id not in source_set1_market_ids
        for quote in result.quotes
    )
