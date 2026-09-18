"""Phase 17.2 end-to-end regressions for football regulation totals."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

from arbiscan.arbitrage import build_opportunity, evaluate_market
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


def _market_id(line: Decimal) -> MarketId:
    return MarketId(f"market:phase17-2:football-total:{line}")


def _over_id(line: Decimal) -> SelectionId:
    return SelectionId(f"selection:phase17-2:over:{line}")


def _under_id(line: Decimal) -> SelectionId:
    return SelectionId(f"selection:phase17-2:under:{line}")


def _registry(*lines: Decimal) -> CanonicalRegistry:
    base = phase16_5._registry()
    markets = list(base.markets)
    selections = list(base.selections)
    for line in lines:
        market = Market(
            id=_market_id(line),
            event_id=phase16_5.EVENT_ID,
            kind=MarketKind.TOTAL_POINTS,
            period=MarketPeriod.REGULATION,
            line=line,
        )
        markets.append(market)
        selections.extend(
            (
                Selection(
                    id=_over_id(line),
                    market_id=market.id,
                    kind=SelectionKind.OVER,
                ),
                Selection(
                    id=_under_id(line),
                    market_id=market.id,
                    kind=SelectionKind.UNDER,
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
    aliases = []
    for provider_id, labels in (
        (
            THE_ODDS_API_PROVIDER_ID,
            ("Pinnacle totals", "Bet365 totals"),
        ),
        (
            ODDSPAPI_PROVIDER_ID,
            ("pinnacle Over Under Full Time", "betfair Over Under Full Time"),
        ),
    ):
        aliases.extend(
            MarketAlias(
                label,
                Sport.FOOTBALL,
                MarketKind.TOTAL_POINTS,
                MarketPeriod.REGULATION,
                provider_id=provider_id,
                requires_line=True,
            )
            for label in labels
        )
    return MarketNormalizer(tuple(aliases))


def _load_the_odds_api(odds_fixture: str) -> _Observation:
    adapter = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture", markets=("totals",)),
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
                "/markets": "markets_phase17_2.json",
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
        assert semantic.value.kind is MarketKind.TOTAL_POINTS
        assert semantic.value.period is MarketPeriod.REGULATION
        assert semantic.value.line == source_market.line

        canonical_market_id = _market_id(source_market.line)
        assert registry.market(canonical_market_id) is not None
        market_ids[source_market.external_market_id] = canonical_market_id
        for source_selection in source_market.selections:
            if source_selection.label.casefold() == "over":
                selection_id = _over_id(source_market.line)
            elif source_selection.label.casefold() == "under":
                selection_id = _under_id(source_market.line)
            else:
                raise AssertionError("unexpected football total selection")
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


def test_two_real_transports_build_same_line_total_arbitrage_end_to_end() -> None:
    line = Decimal("2.5")
    registry = _registry(line)
    observations = (
        _load_the_odds_api("odds_event_phase17_2_totals.json"),
        _load_oddspapi("odds_fixture_phase17_2_totals.json"),
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
    assert {
        quote.provider_id for quote in consolidated
    } == {PINNACLE_ID, BET365_ID, BETFAIR_ID}

    batch = build_market_books(
        consolidated,
        registry=registry,
        as_of=phase16_5.AS_OF,
        freshness_window=phase16_5.FRESHNESS_WINDOW,
        market_ids=(_market_id(line),),
    )
    assert len(batch.books) == 1
    book = batch.books[0]
    assert book.expected_selection_ids == tuple(
        sorted((_over_id(line), _under_id(line)), key=lambda value: value.value)
    )

    selected = {outcome.selection.id: outcome.quote for outcome in book.outcomes}
    assert selected[_over_id(line)].provider_id == BET365_ID
    assert selected[_over_id(line)].decimal_price == Decimal("2.10")
    assert selected[_over_id(line)].transport_provider_id == THE_ODDS_API_PROVIDER_ID

    assert selected[_under_id(line)].provider_id == BETFAIR_ID
    assert selected[_under_id(line)].decimal_price == Decimal("2.05")
    assert selected[_under_id(line)].transport_provider_id == ODDSPAPI_PROVIDER_ID

    evaluation = evaluate_market(book.quotes, book.expected_selection_ids)
    assert evaluation.is_arbitrage
    assert evaluation.implied_probability_sum < Decimal("1")

    opportunity = build_opportunity(
        evaluation,
        opportunity_id=OpportunityId("opportunity:phase17-2:football-total-2.5"),
        detected_at=phase16_5.AS_OF,
    )
    assert opportunity.market_id == _market_id(line)
    assert set(opportunity.quote_ids) == {quote.id for quote in book.quotes}


def test_different_total_lines_cannot_complete_each_other() -> None:
    line_25 = Decimal("2.5")
    line_35 = Decimal("3.5")
    registry = _registry(line_25, line_35)
    odds_25, issues_25 = _normalize(
        _load_the_odds_api("odds_event_phase17_2_totals.json"),
        registry,
    )
    odds_35, issues_35 = _normalize(
        _load_oddspapi("odds_fixture_phase17_2_total_3_5.json"),
        registry,
    )
    assert issues_25 == ()
    assert issues_35 == ()

    over_25 = next(quote for quote in odds_25 if quote.selection_id == _over_id(line_25))
    under_35 = next(quote for quote in odds_35 if quote.selection_id == _under_id(line_35))

    batch = build_market_books(
        (over_25, under_35),
        registry=registry,
        as_of=phase16_5.AS_OF,
        freshness_window=phase16_5.FRESHNESS_WINDOW,
        market_ids=(_market_id(line_25), _market_id(line_35)),
    )

    assert batch.books == ()
    incomplete = {
        diagnostic.market_id
        for diagnostic in batch.diagnostics
        if diagnostic.code is MarketBookDiagnosticCode.INCOMPLETE_MARKET
    }
    assert incomplete == {_market_id(line_25), _market_id(line_35)}


def test_integer_total_is_rejected_even_with_explicit_canonical_mapping() -> None:
    line = Decimal("3")
    registry = _registry(line)
    observation = _load_oddspapi("odds_fixture_phase17_2_integer_total.json")

    quotes, issues = _normalize(observation, registry)

    assert quotes == ()
    assert issues == (
        NormalizationIssueCode.UNSUPPORTED_MARKET_VARIANT,
        NormalizationIssueCode.UNSUPPORTED_MARKET_VARIANT,
    )
