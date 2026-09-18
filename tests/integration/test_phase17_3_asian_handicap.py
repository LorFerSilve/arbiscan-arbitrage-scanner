"""Phase 17.3 end-to-end regressions for football Asian handicap semantics."""

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
from arbiscan.marketbook import MarketBookDiagnosticCode, build_market_books
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

BET365_ID = ProviderId("bookmaker:the-odds-api:bet365")
BETFAIR_ID = ProviderId("bookmaker:the-odds-api:betfair")
PINNACLE_ID = ProviderId("bookmaker:the-odds-api:pinnacle")


@dataclass(frozen=True, slots=True)
class _Observation:
    adapter: ProviderAdapter
    competition: SourceCompetition
    event: SourceEvent
    snapshot: OddsSnapshot


def _line_slug(line: Decimal) -> str:
    return str(line).replace("-", "minus-")


def _market_id(line: Decimal) -> MarketId:
    return MarketId(f"market:phase17-3:football-ah:{_line_slug(line)}")


def _home_id(line: Decimal) -> SelectionId:
    return SelectionId(f"selection:phase17-3:home:{_line_slug(line)}")


def _away_id(line: Decimal) -> SelectionId:
    return SelectionId(f"selection:phase17-3:away:{_line_slug(line)}")


def _registry(*lines: Decimal) -> CanonicalRegistry:
    base = phase16_5._registry()
    markets = list(base.markets)
    selections = list(base.selections)
    for line in lines:
        market = Market(
            id=_market_id(line),
            event_id=phase16_5.EVENT_ID,
            kind=MarketKind.HANDICAP,
            period=MarketPeriod.REGULATION,
            line=line,
        )
        markets.append(market)
        selections.extend(
            (
                Selection(
                    id=_home_id(line),
                    market_id=market.id,
                    kind=SelectionKind.PARTICIPANT,
                    participant_id=phase16_5.LIVERPOOL_ID,
                    handicap=line,
                ),
                Selection(
                    id=_away_id(line),
                    market_id=market.id,
                    kind=SelectionKind.PARTICIPANT,
                    participant_id=phase16_5.MANCHESTER_UNITED_ID,
                    handicap=-line,
                ),
            )
        )
    return CanonicalRegistry(
        competitions=base.competitions,
        participants=base.participants,
        events=base.events,
        markets=tuple(markets),
        selections=tuple(selections),
    )


def _market_normalizer() -> MarketNormalizer:
    aliases: list[MarketAlias] = []
    for provider_id, labels in (
        (
            THE_ODDS_API_PROVIDER_ID,
            ("Pinnacle spreads", "Bet365 spreads"),
        ),
        (
            ODDSPAPI_PROVIDER_ID,
            ("pinnacle Asian Handicap", "betfair Asian Handicap"),
        ),
    ):
        aliases.extend(
            MarketAlias(
                label,
                Sport.FOOTBALL,
                MarketKind.HANDICAP,
                MarketPeriod.REGULATION,
                provider_id=provider_id,
                requires_line=True,
            )
            for label in labels
        )
    return MarketNormalizer(tuple(aliases))


def _load_the_odds_api(odds_fixture: str) -> _Observation:
    adapter = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture", markets=("spreads",)),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={
                "events": "events_soccer_epl_phase16_5.json",
                "odds": odds_fixture,
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


def _load_oddspapi(odds_fixture: str) -> _Observation:
    adapter = OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture"),
        transport=OddsPapiFixtureTransport(
            fixture_overrides={
                "/markets": "markets_phase17_3.json",
                "/odds": odds_fixture,
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


def _canonical_selection_id(
    provider_id: ProviderId,
    label: str,
    line: Decimal,
) -> SelectionId:
    if provider_id == THE_ODDS_API_PROVIDER_ID:
        if label == "Liverpool FC":
            return _home_id(line)
        if label == "Manchester United":
            return _away_id(line)
    elif provider_id == ODDSPAPI_PROVIDER_ID:
        if label == "1":
            return _home_id(line)
        if label == "2":
            return _away_id(line)
    raise AssertionError(f"unexpected handicap selection label {label!r}")


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
        assert source_market.line is not None
        semantic = normalizer.resolve(
            source_market.label,
            sport=Sport.FOOTBALL,
            provider_id=observation.adapter.provider.id,
            line=source_market.line,
        )
        assert semantic.status is ResolutionStatus.RESOLVED
        assert semantic.value is not None
        assert semantic.value.kind is MarketKind.HANDICAP
        assert semantic.value.period is MarketPeriod.REGULATION
        assert semantic.value.line == source_market.line

        canonical_market_id = _market_id(source_market.line)
        assert registry.market(canonical_market_id) is not None
        market_ids[source_market.external_market_id] = canonical_market_id
        for source_selection in source_market.selections:
            selection_id = _canonical_selection_id(
                observation.adapter.provider.id,
                source_selection.label,
                source_market.line,
            )
            selection_ids[
                (source_market.external_market_id, source_selection.external_selection_id)
            ] = selection_id

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


def test_half_goal_asian_handicap_runs_end_to_end_through_existing_stake_allocator() -> None:
    line = Decimal("-0.5")
    registry = _registry(line)
    observations = (
        _load_the_odds_api("odds_event_phase17_3_handicap.json"),
        _load_oddspapi("odds_fixture_phase17_3_handicap.json"),
    )

    normalized: list[OddsQuote] = []
    for observation in observations:
        quotes, issues = _normalize(observation, registry)
        assert issues == ()
        assert quotes
        assert {quote.market_id for quote in quotes} == {_market_id(line)}
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
        market_ids=(_market_id(line),),
    )
    assert len(batch.books) == 1
    book = batch.books[0]

    selected = {outcome.selection.id: outcome.quote for outcome in book.outcomes}
    assert selected[_home_id(line)].provider_id == BET365_ID
    assert selected[_home_id(line)].decimal_price == Decimal("2.10")
    assert selected[_home_id(line)].transport_provider_id == THE_ODDS_API_PROVIDER_ID
    assert selected[_away_id(line)].provider_id == BETFAIR_ID
    assert selected[_away_id(line)].decimal_price == Decimal("2.05")
    assert selected[_away_id(line)].transport_provider_id == ODDSPAPI_PROVIDER_ID

    evaluation = evaluate_market(book.quotes, book.expected_selection_ids)
    assert evaluation.is_arbitrage

    opportunity = build_opportunity(
        evaluation,
        opportunity_id=OpportunityId("opportunity:phase17-3:football-ah-minus-0.5"),
        detected_at=phase16_5.AS_OF,
    )
    plan = allocate_stakes(
        opportunity,
        evaluation.quotes,
        bankroll=Decimal("100"),
        stake_plan_id=StakePlanId("stake-plan:phase17-3:football-ah-minus-0.5"),
        created_at=phase16_5.AS_OF,
        rounding_policy=CurrencyRoundingPolicy(currency="EUR"),
    )

    assert plan is not None
    assert plan.guaranteed_profit > Decimal("0")
    assert plan.guaranteed_payout > plan.bankroll


def test_opposite_anchored_lines_are_distinct_markets_and_cannot_complete_each_other() -> None:
    minus = Decimal("-0.5")
    plus = Decimal("0.5")
    registry = _registry(minus, plus)
    minus_quotes, minus_issues = _normalize(
        _load_the_odds_api("odds_event_phase17_3_handicap.json"),
        registry,
    )
    plus_quotes, plus_issues = _normalize(
        _load_oddspapi("odds_fixture_phase17_3_handicap_plus_0_5.json"),
        registry,
    )
    assert minus_issues == ()
    assert plus_issues == ()

    home_minus = next(quote for quote in minus_quotes if quote.selection_id == _home_id(minus))
    away_plus = next(quote for quote in plus_quotes if quote.selection_id == _away_id(plus))

    batch = build_market_books(
        (home_minus, away_plus),
        registry=registry,
        as_of=phase16_5.AS_OF,
        freshness_window=phase16_5.FRESHNESS_WINDOW,
        market_ids=(_market_id(minus), _market_id(plus)),
    )

    assert batch.books == ()
    incomplete = {
        diagnostic.market_id
        for diagnostic in batch.diagnostics
        if diagnostic.code is MarketBookDiagnosticCode.INCOMPLETE_MARKET
    }
    assert incomplete == {_market_id(minus), _market_id(plus)}


def test_integer_handicap_push_variant_is_rejected_before_quote_construction() -> None:
    line = Decimal("0")
    registry = _registry(line)
    observation = _load_oddspapi("odds_fixture_phase17_3_handicap_zero.json")

    quotes, issues = _normalize(observation, registry)

    assert quotes == ()
    assert issues == (
        NormalizationIssueCode.UNSUPPORTED_MARKET_VARIANT,
        NormalizationIssueCode.UNSUPPORTED_MARKET_VARIANT,
    )


def test_quarter_handicap_split_variant_is_rejected_before_quote_construction() -> None:
    line = Decimal("-0.25")
    registry = _registry(line)
    observation = _load_oddspapi("odds_fixture_phase17_3_handicap_quarter.json")

    quotes, issues = _normalize(observation, registry)

    assert quotes == ()
    assert issues == (
        NormalizationIssueCode.UNSUPPORTED_MARKET_VARIANT,
        NormalizationIssueCode.UNSUPPORTED_MARKET_VARIANT,
    )
