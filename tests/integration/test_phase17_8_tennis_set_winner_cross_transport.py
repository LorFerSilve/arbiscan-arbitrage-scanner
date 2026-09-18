"""Phase 17.8 tennis set-winner cross-transport completion regressions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from arbiscan.arbitrage import (
    CurrencyRoundingPolicy,
    allocate_stakes,
    build_opportunity,
    evaluate_market,
)
from arbiscan.domain import (
    MarketId,
    MarketKind,
    MarketPeriod,
    OddsQuote,
    OpportunityId,
    ParticipantKind,
    ProviderId,
    SelectionId,
    Sport,
    StakePlanId,
)
from arbiscan.ingestion import ConsolidationDiagnosticCode, consolidate_quotes
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
from tests.integration import test_phase16_5_tennis_semantics as phase16_tennis
from tests.integration import test_phase17_6_tennis_set_winner as phase17_6
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as TheOddsApiFixtureTransport

PINNACLE_ID = ProviderId("bookmaker:the-odds-api:pinnacle")
BET365_ID = ProviderId("bookmaker:the-odds-api:bet365")
BETFAIR_ID = ProviderId("bookmaker:the-odds-api:betfair")


@dataclass(frozen=True, slots=True)
class _Observation:
    adapter: ProviderAdapter
    competition: SourceCompetition
    event: SourceEvent
    snapshot: OddsSnapshot


def _market_normalizer() -> MarketNormalizer:
    aliases: list[MarketAlias] = []
    for bookmaker in ("Pinnacle", "Bet365"):
        for key in ("h2h_s1", "h2h_s2"):
            aliases.append(
                MarketAlias(
                    f"{bookmaker} {key}",
                    Sport.TENNIS,
                    MarketKind.SET_WINNER,
                    MarketPeriod.SET,
                    provider_id=THE_ODDS_API_PROVIDER_ID,
                    requires_period_index=True,
                )
            )
    for bookmaker in ("pinnacle", "betfair"):
        for name in ("First Set Winner", "Second Set Winner"):
            aliases.append(
                MarketAlias(
                    f"{bookmaker} {name}",
                    Sport.TENNIS,
                    MarketKind.SET_WINNER,
                    MarketPeriod.SET,
                    provider_id=ODDSPAPI_PROVIDER_ID,
                    requires_period_index=True,
                )
            )
    return MarketNormalizer(tuple(aliases))


def _load_observations() -> tuple[_Observation, _Observation]:
    the_odds_api = TheOddsApiProvider(
        config=TheOddsApiConfig(
            api_key="fixture",
            markets=("h2h_s1", "h2h_s2"),
        ),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={
                "events": "events_tennis_atp_us_open_phase16_5.json",
                "odds": "odds_event_phase17_8_tennis_sets.json",
            }
        ),
        clock=lambda: phase16_tennis.AS_OF,
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
                "/markets": "markets_phase17_6_tennis_sets.json",
                "/odds": "odds_fixture_phase17_8_tennis_sets.json",
            }
        ),
        clock=lambda: phase16_tennis.AS_OF,
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


def _market_id(period_index: int) -> MarketId:
    return phase17_6._market_id(period_index)


def _selection_id(
    provider_id: ProviderId,
    period_index: int,
    label: str,
) -> SelectionId:
    if provider_id == THE_ODDS_API_PROVIDER_ID:
        if period_index == 1:
            return {
                "Jannik Sinner": phase17_6.SET1_SINNER_ID,
                "Carlos Alcaraz": phase17_6.SET1_ALCARAZ_ID,
            }[label]
        if period_index == 2:
            return {
                "Jannik Sinner": phase17_6.SET2_SINNER_ID,
                "Carlos Alcaraz": phase17_6.SET2_ALCARAZ_ID,
            }[label]
        raise AssertionError(f"unexpected set index {period_index}")
    if provider_id == ODDSPAPI_PROVIDER_ID:
        return phase17_6._selection_id(period_index, label)
    raise AssertionError(f"unexpected provider {provider_id}")


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
            provider_id=observation.adapter.provider.id,
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
            ] = _selection_id(
                observation.adapter.provider.id,
                source_market.period_index,
                source_selection.label,
            )

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
) -> tuple[OddsQuote, ...]:
    result = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=_hooks(observation, registry),
        event=observation.event,
        snapshot=observation.snapshot,
        registry=registry,
        as_of=phase16_tennis.AS_OF,
        freshness_window=phase16_tennis.FRESHNESS_WINDOW,
    )
    assert result.issues == ()
    return result.quotes


def test_cross_transport_set_winners_consolidate_overlap_and_keep_sets_isolated() -> None:
    registry = phase17_6._registry()
    observations = _load_observations()
    normalized = {
        observation.adapter.provider.id: _normalize(observation, registry)
        for observation in observations
    }

    assert len(normalized[THE_ODDS_API_PROVIDER_ID]) == 8
    assert len(normalized[ODDSPAPI_PROVIDER_ID]) == 8

    all_quotes = (
        *normalized[THE_ODDS_API_PROVIDER_ID],
        *normalized[ODDSPAPI_PROVIDER_ID],
    )
    result = consolidate_quotes(all_quotes)

    assert result.conflict_count == 0
    assert result.equivalent_overlap_count == 4
    assert len(result.quotes) == 12
    equivalent = tuple(
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.code is ConsolidationDiagnosticCode.EQUIVALENT_OVERLAP
    )
    assert len(equivalent) == 4
    assert all(
        set(diagnostic.transport_provider_ids) == {THE_ODDS_API_PROVIDER_ID, ODDSPAPI_PROVIDER_ID}
        for diagnostic in equivalent
    )

    pinnacle = tuple(quote for quote in result.quotes if quote.provider_id == PINNACLE_ID)
    assert len(pinnacle) == 4
    assert {(quote.market_id, quote.selection_id) for quote in pinnacle} == {
        (phase17_6.SET1_MARKET_ID, phase17_6.SET1_SINNER_ID),
        (phase17_6.SET1_MARKET_ID, phase17_6.SET1_ALCARAZ_ID),
        (phase17_6.SET2_MARKET_ID, phase17_6.SET2_SINNER_ID),
        (phase17_6.SET2_MARKET_ID, phase17_6.SET2_ALCARAZ_ID),
    }
    assert all(
        quote.transport_provider_id in {THE_ODDS_API_PROVIDER_ID, ODDSPAPI_PROVIDER_ID}
        for quote in pinnacle
    )

    batch = build_market_books(
        result.quotes,
        registry=registry,
        as_of=phase16_tennis.AS_OF,
        freshness_window=phase16_tennis.FRESHNESS_WINDOW,
        market_ids=(phase17_6.SET1_MARKET_ID, phase17_6.SET2_MARKET_ID),
    )
    assert len(batch.books) == 2
    books = {book.market.id: book for book in batch.books}
    assert set(books) == {phase17_6.SET1_MARKET_ID, phase17_6.SET2_MARKET_ID}

    set1 = books[phase17_6.SET1_MARKET_ID]
    set1_selected = {outcome.selection.id: outcome.quote for outcome in set1.outcomes}
    assert set1_selected[phase17_6.SET1_ALCARAZ_ID].provider_id == BETFAIR_ID
    assert set1_selected[phase17_6.SET1_ALCARAZ_ID].transport_provider_id == ODDSPAPI_PROVIDER_ID
    assert set1_selected[phase17_6.SET1_ALCARAZ_ID].decimal_price == Decimal("2.10")
    assert set1_selected[phase17_6.SET1_SINNER_ID].provider_id == PINNACLE_ID
    assert set1_selected[phase17_6.SET1_SINNER_ID].decimal_price == Decimal("2.05")

    evaluation = evaluate_market(set1.quotes, set1.expected_selection_ids)
    assert evaluation.is_arbitrage
    opportunity = build_opportunity(
        evaluation,
        opportunity_id=OpportunityId("opportunity:phase17-8:tennis:set1"),
        detected_at=phase16_tennis.AS_OF,
    )
    plan = allocate_stakes(
        opportunity,
        evaluation.quotes,
        bankroll=Decimal("100"),
        stake_plan_id=StakePlanId("stake-plan:phase17-8:tennis:set1"),
        created_at=phase16_tennis.AS_OF,
        rounding_policy=CurrencyRoundingPolicy(currency="EUR"),
    )
    assert plan is not None
    assert plan.guaranteed_profit > Decimal("0")

    set2 = books[phase17_6.SET2_MARKET_ID]
    set2_selected = {outcome.selection.id: outcome.quote for outcome in set2.outcomes}
    assert set2_selected[phase17_6.SET2_ALCARAZ_ID].provider_id == BET365_ID
    assert (
        set2_selected[phase17_6.SET2_ALCARAZ_ID].transport_provider_id == THE_ODDS_API_PROVIDER_ID
    )
    assert set2_selected[phase17_6.SET2_ALCARAZ_ID].decimal_price == Decimal("1.92")
    assert set2_selected[phase17_6.SET2_SINNER_ID].provider_id == PINNACLE_ID
    assert set2_selected[phase17_6.SET2_SINNER_ID].decimal_price == Decimal("1.94")
    assert not evaluate_market(
        set2.quotes,
        set2.expected_selection_ids,
    ).is_arbitrage


def test_the_odds_api_set_one_cannot_be_mapped_to_canonical_set_two() -> None:
    registry = phase17_6._registry()
    the_odds_api, _oddspapi = _load_observations()
    hooks = _hooks(the_odds_api, registry)
    base = cast(StaticCanonicalIdHooks, hooks.base)

    set1_source_ids = {
        market.external_market_id
        for market in the_odds_api.snapshot.markets
        if market.period_index == 1
    }
    remapped = dict(base.market_ids)
    for source_market_id in set1_source_ids:
        remapped[source_market_id] = phase17_6.SET2_MARKET_ID

    mismatched = MatchedCanonicalIdHooks(
        base=StaticCanonicalIdHooks(
            competition_ids=base.competition_ids,
            market_ids=remapped,
            selection_ids=base.selection_ids,
        ),
        event_decisions=hooks.event_decisions,
    )
    result = normalize_source_snapshot(
        provider=the_odds_api.adapter.provider,
        hooks=mismatched,
        event=the_odds_api.event,
        snapshot=the_odds_api.snapshot,
        registry=registry,
        as_of=phase16_tennis.AS_OF,
        freshness_window=phase16_tennis.FRESHNESS_WINDOW,
    )

    set1_issues = tuple(
        issue for issue in result.issues if issue.external_market_id in set1_source_ids
    )
    assert len(set1_issues) == 2
    assert {issue.code for issue in set1_issues} == {
        NormalizationIssueCode.MARKET_PARAMETER_MISMATCH
    }
    assert all(quote.source_market_id not in set1_source_ids for quote in result.quotes)
