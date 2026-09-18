"""Phase 17.5 end-to-end Draw No Bet settlement-aware regressions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

from arbiscan.arbitrage import evaluate_market, evaluate_refundable_two_way_market
from arbiscan.domain import (
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    OddsQuote,
    ParticipantKind,
    ProviderId,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
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
    MarketSupportPurpose,
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

MARKET_ID = MarketId("market:phase17-5:football-dnb")
HOME_ID = SelectionId("selection:phase17-5:dnb:home")
AWAY_ID = SelectionId("selection:phase17-5:dnb:away")
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
        kind=MarketKind.HANDICAP,
        period=MarketPeriod.REGULATION,
        line=Decimal("0"),
    )
    home = Selection(
        id=HOME_ID,
        market_id=market.id,
        kind=SelectionKind.PARTICIPANT,
        participant_id=phase16_5.LIVERPOOL_ID,
        handicap=Decimal("0"),
    )
    away = Selection(
        id=AWAY_ID,
        market_id=market.id,
        kind=SelectionKind.PARTICIPANT,
        participant_id=phase16_5.MANCHESTER_UNITED_ID,
        handicap=Decimal("0"),
    )
    return CanonicalRegistry(
        competitions=base.competitions,
        participants=base.participants,
        events=base.events,
        markets=(*base.markets, market),
        selections=(*base.selections, home, away),
    )


def _market_normalizer() -> MarketNormalizer:
    aliases: list[MarketAlias] = []
    for provider_id, labels in (
        (
            THE_ODDS_API_PROVIDER_ID,
            ("Pinnacle draw_no_bet", "Bet365 draw_no_bet"),
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


def _load_the_odds_api() -> _Observation:
    adapter = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture", markets=("draw_no_bet",)),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={
                "events": "events_soccer_epl_phase16_5.json",
                "odds": "odds_event_phase17_5_dnb.json",
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
                "/markets": "markets_phase17_5.json",
                "/odds": "odds_fixture_phase17_5_dnb.json",
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


def _selection_id(provider_id: ProviderId, label: str) -> SelectionId:
    if provider_id == THE_ODDS_API_PROVIDER_ID:
        if label == "Liverpool FC":
            return HOME_ID
        if label == "Manchester United":
            return AWAY_ID
    elif provider_id == ODDSPAPI_PROVIDER_ID:
        if label == "1":
            return HOME_ID
        if label == "2":
            return AWAY_ID
    raise AssertionError(f"unexpected Draw No Bet selection label {label!r}")


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
        assert source_market.line == Decimal("0")
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
        assert semantic.value.line == Decimal("0")

        market_ids[source_market.external_market_id] = MARKET_ID
        for source_selection in source_market.selections:
            assert source_selection.handicap == Decimal("0")
            selection_ids[
                (source_market.external_market_id, source_selection.external_selection_id)
            ] = _selection_id(
                observation.adapter.provider.id,
                source_selection.label,
            )

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
    *,
    purpose: MarketSupportPurpose,
) -> tuple[tuple[OddsQuote, ...], tuple[NormalizationIssueCode, ...]]:
    result = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=_hooks(observation, registry),
        event=observation.event,
        snapshot=observation.snapshot,
        registry=registry,
        as_of=phase16_5.AS_OF,
        freshness_window=phase16_5.FRESHNESS_WINDOW,
        support_purpose=purpose,
    )
    return result.quotes, tuple(issue.code for issue in result.issues)


def test_draw_no_bet_remains_blocked_from_generic_normalization_path() -> None:
    registry = _registry()

    for observation in (_load_the_odds_api(), _load_oddspapi()):
        quotes, issues = _normalize(
            observation,
            registry,
            purpose=MarketSupportPurpose.GENERIC_ARBITRAGE,
        )

        assert quotes == ()
        assert issues
        assert set(issues) == {NormalizationIssueCode.UNSUPPORTED_MARKET_VARIANT}


def test_two_real_transports_build_same_dnb_book_for_refundable_evaluation() -> None:
    registry = _registry()
    observations = (_load_the_odds_api(), _load_oddspapi())

    normalized: list[OddsQuote] = []
    for observation in observations:
        quotes, issues = _normalize(
            observation,
            registry,
            purpose=MarketSupportPurpose.SETTLEMENT_AWARE,
        )
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
    assert set(book.expected_selection_ids) == {HOME_ID, AWAY_ID}

    selected = {outcome.selection.id: outcome.quote for outcome in book.outcomes}
    assert selected[HOME_ID].provider_id == BET365_ID
    assert selected[HOME_ID].decimal_price == Decimal("2.10")
    assert selected[HOME_ID].transport_provider_id == THE_ODDS_API_PROVIDER_ID
    assert selected[AWAY_ID].provider_id == BETFAIR_ID
    assert selected[AWAY_ID].decimal_price == Decimal("2.05")
    assert selected[AWAY_ID].transport_provider_id == ODDSPAPI_PROVIDER_ID

    reciprocal_prefilter = evaluate_market(book.quotes, book.expected_selection_ids)
    assert reciprocal_prefilter.is_arbitrage
    assert reciprocal_prefilter.theoretical_profit_margin > Decimal("0")

    settlement = evaluate_refundable_two_way_market(
        book.quotes,
        book.expected_selection_ids,
    )
    assert settlement.is_refundable_arbitrage
    assert settlement.decisive_profit_margin > Decimal("0")
    assert settlement.refund_return_multiplier == Decimal("1")
    assert settlement.worst_case_return_multiplier == Decimal("1")
    assert settlement.worst_case_profit_margin == Decimal("0")
    assert not settlement.has_strict_guaranteed_profit
