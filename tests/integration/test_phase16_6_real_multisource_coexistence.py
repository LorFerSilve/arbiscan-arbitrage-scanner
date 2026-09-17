"""Phase 16.6 regressions for coexistence of the two real source adapters."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from arbiscan.arbitrage import build_opportunity, evaluate_market
from arbiscan.domain import (
    OddsQuote,
    OpportunityId,
    ParticipantKind,
    ProviderId,
    QuoteStatus,
    SelectionId,
    Sport,
)
from arbiscan.ingestion import (
    ConsolidationDiagnosticCode,
    MultiSourceLiveQuoteStore,
    RealtimeIngestionPolicy,
    RealtimeIngestionRuntime,
    consolidate_quotes,
)
from arbiscan.marketbook import ProviderBookPolicy, build_market_books
from arbiscan.matching import (
    CanonicalRegistry,
    EventMatchDecision,
    EventMatcher,
    EventMatchStatus,
    MatchedCanonicalIdHooks,
    ParticipantOrderPolicy,
    StaticCanonicalIdHooks,
)
from arbiscan.normalization import normalize_source_snapshot, prepare_event_evidence
from arbiscan.persistence import SqliteAuditStore
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


@dataclass(frozen=True, slots=True)
class _Observation:
    adapter: ProviderAdapter
    competition: SourceCompetition
    event: SourceEvent
    snapshot: OddsSnapshot


def _load_observations() -> tuple[_Observation, _Observation]:
    the_odds_api = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture"),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={
                "events": "events_soccer_epl_phase16_5.json",
                "odds": "odds_event_phase16_6.json",
            }
        ),
        clock=lambda: phase16_5.AS_OF,
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
        transport=OddsPapiFixtureTransport(
            fixture_overrides={"/odds": "odds_fixture_phase16_6.json"}
        ),
        clock=lambda: phase16_5.AS_OF,
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


def _hooks_for_observation(
    observation: _Observation,
    registry: CanonicalRegistry,
) -> tuple[MatchedCanonicalIdHooks, EventMatchDecision]:
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

    market_ids = {}
    selection_ids: dict[tuple[str, str], SelectionId] = {}
    for source_market in observation.snapshot.markets:
        if observation.adapter.provider.id == THE_ODDS_API_PROVIDER_ID:
            assert source_market.label.casefold().endswith(" h2h")
        else:
            assert observation.adapter.provider.id == ODDSPAPI_PROVIDER_ID
            assert source_market.label.casefold().endswith(" full time result")

        market_ids[source_market.external_market_id] = phase16_5.MARKET_ID
        for source_selection in source_market.selections:
            selection_id = phase16_5._selection_id(
                observation.adapter.provider.id,
                source_selection.label,
            )
            assert selection_id is not None
            selection_ids[
                (source_market.external_market_id, source_selection.external_selection_id)
            ] = selection_id

    base = StaticCanonicalIdHooks(
        competition_ids={
            observation.competition.external_id: phase16_5.COMPETITION_ID,
        },
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


def _normalize_observation(
    observation: _Observation,
    registry: CanonicalRegistry,
) -> tuple[OddsQuote, ...]:
    hooks, decision = _hooks_for_observation(observation, registry)
    assert decision.confidence_bps is not None
    normalized = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=hooks,
        event=observation.event,
        snapshot=observation.snapshot,
        registry=registry,
        as_of=phase16_5.AS_OF,
        freshness_window=phase16_5.FRESHNESS_WINDOW,
    )
    assert normalized.issues == ()
    assert len(normalized.quotes) == 6
    return normalized.quotes


def _real_quotes() -> tuple[
    CanonicalRegistry,
    tuple[_Observation, _Observation],
    dict[ProviderId, tuple[OddsQuote, ...]],
]:
    registry = phase16_5._registry()
    observations = _load_observations()
    quotes = {
        observation.adapter.provider.id: _normalize_observation(observation, registry)
        for observation in observations
    }
    return registry, observations, quotes


def _flatten(quotes: dict[ProviderId, tuple[OddsQuote, ...]]) -> tuple[OddsQuote, ...]:
    return tuple(
        quote
        for provider_id in sorted(quotes, key=lambda value: value.value)
        for quote in quotes[provider_id]
    )


def _store(quotes: tuple[OddsQuote, ...]) -> MultiSourceLiveQuoteStore:
    store = MultiSourceLiveQuoteStore(
        RealtimeIngestionPolicy(freshness_window=phase16_5.FRESHNESS_WINDOW)
    )
    result = store.apply(quotes, observed_at=phase16_5.AS_OF)
    assert result.rejected_count == 0
    return store


def _quote(
    quotes: dict[ProviderId, tuple[OddsQuote, ...]],
    *,
    transport_provider_id: ProviderId,
    price_provider_id: ProviderId,
    selection_id: SelectionId,
) -> OddsQuote:
    return next(
        quote
        for quote in quotes[transport_provider_id]
        if quote.provider_id == price_provider_id and quote.selection_id == selection_id
    )


def _book(
    registry: CanonicalRegistry,
    quotes: tuple[OddsQuote, ...],
    *,
    provider_policy: ProviderBookPolicy | None = None,
):
    batch = build_market_books(
        quotes,
        registry=registry,
        as_of=phase16_5.AS_OF,
        freshness_window=phase16_5.FRESHNESS_WINDOW,
        provider_policy=provider_policy,
        market_ids=(phase16_5.MARKET_ID,),
    )
    assert len(batch.books) == 1
    return batch.books[0]


def test_real_sources_contribute_distinct_best_prices_to_one_market_book() -> None:
    registry, _observations, quotes = _real_quotes()
    store = _store(_flatten(quotes))

    assert len(store.fresh_observations(as_of=phase16_5.AS_OF)) == 12
    consolidated = store.fresh_quotes(as_of=phase16_5.AS_OF)
    assert len(consolidated) == 9

    book = _book(registry, consolidated)
    selected = {outcome.selection.id: outcome.quote for outcome in book.outcomes}

    assert selected[phase16_5.HOME_SELECTION_ID].provider_id == BET365_ID
    assert selected[phase16_5.HOME_SELECTION_ID].decimal_price == Decimal("2.70")
    assert (
        selected[phase16_5.HOME_SELECTION_ID].transport_provider_id
        == THE_ODDS_API_PROVIDER_ID
    )

    assert selected[phase16_5.DRAW_SELECTION_ID].provider_id == phase16_5.PINNACLE_ID
    assert selected[phase16_5.DRAW_SELECTION_ID].decimal_price == Decimal("3.25")
    assert (
        selected[phase16_5.DRAW_SELECTION_ID].transport_provider_id
        == THE_ODDS_API_PROVIDER_ID
    )

    assert selected[phase16_5.AWAY_SELECTION_ID].provider_id == BETFAIR_ID
    assert selected[phase16_5.AWAY_SELECTION_ID].decimal_price == Decimal("3.4")
    assert selected[phase16_5.AWAY_SELECTION_ID].transport_provider_id == ODDSPAPI_PROVIDER_ID


def test_real_provider_outage_is_isolated_from_the_other_source() -> None:
    unavailable = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture"),
        transport=TheOddsApiFixtureTransport(status_code=503),
        clock=lambda: phase16_5.AS_OF,
    )
    healthy = OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture"),
        transport=OddsPapiFixtureTransport(
            fixture_overrides={"/odds": "odds_fixture_phase16_6.json"}
        ),
        clock=lambda: phase16_5.AS_OF,
    )
    policy = RealtimeIngestionPolicy(freshness_window=phase16_5.FRESHNESS_WINDOW)
    runtime = RealtimeIngestionRuntime(policy=policy, clock=lambda: phase16_5.AS_OF)

    batch = asyncio.run(runtime.poll_once((unavailable, healthy), Sport.FOOTBALL))

    assert batch.ingestion.snapshots
    assert {
        snapshot.provider.id for snapshot in batch.ingestion.snapshots
    } == {ODDSPAPI_PROVIDER_ID}
    assert any(
        issue.provider_id == THE_ODDS_API_PROVIDER_ID for issue in batch.ingestion.issues
    )
    metrics = {metric.provider_id: metric for metric in batch.provider_metrics}
    assert metrics[THE_ODDS_API_PROVIDER_ID].snapshot_count == 0
    assert metrics[THE_ODDS_API_PROVIDER_ID].issue_count > 0
    assert metrics[ODDSPAPI_PROVIDER_ID].snapshot_count > 0


def test_stale_real_source_cannot_override_fresher_eligible_observation() -> None:
    _registry, _observations, quotes = _real_quotes()
    stale = _quote(
        quotes,
        transport_provider_id=ODDSPAPI_PROVIDER_ID,
        price_provider_id=phase16_5.PINNACLE_ID,
        selection_id=phase16_5.AWAY_SELECTION_ID,
    )
    fresh = _quote(
        quotes,
        transport_provider_id=THE_ODDS_API_PROVIDER_ID,
        price_provider_id=phase16_5.PINNACLE_ID,
        selection_id=phase16_5.AWAY_SELECTION_ID,
    )
    stale = replace(
        stale,
        decimal_price=Decimal("9.99"),
        source_timestamp=phase16_5.AS_OF - timedelta(minutes=3),
        ingested_at=phase16_5.AS_OF - timedelta(minutes=3),
    )
    store = _store((stale, fresh))

    assert store.fresh_quotes(as_of=phase16_5.AS_OF) == (fresh,)


def test_shared_bookmaker_is_never_counted_twice_across_real_transports() -> None:
    _registry, _observations, quotes = _real_quotes()
    store = _store(_flatten(quotes))

    observations = tuple(
        quote
        for quote in store.fresh_observations(as_of=phase16_5.AS_OF)
        if quote.provider_id == phase16_5.PINNACLE_ID
    )
    executable = tuple(
        quote
        for quote in store.fresh_quotes(as_of=phase16_5.AS_OF)
        if quote.provider_id == phase16_5.PINNACLE_ID
    )

    assert len(observations) == 6
    assert {quote.transport_provider_id for quote in observations} == {
        THE_ODDS_API_PROVIDER_ID,
        ODDSPAPI_PROVIDER_ID,
    }
    assert len(executable) == 3
    assert {quote.selection_id for quote in executable} == {
        phase16_5.HOME_SELECTION_ID,
        phase16_5.DRAW_SELECTION_ID,
        phase16_5.AWAY_SELECTION_ID,
    }


def test_equal_time_real_source_conflict_fails_closed_with_diagnostics() -> None:
    _registry, _observations, quotes = _real_quotes()
    first = _quote(
        quotes,
        transport_provider_id=THE_ODDS_API_PROVIDER_ID,
        price_provider_id=phase16_5.PINNACLE_ID,
        selection_id=phase16_5.HOME_SELECTION_ID,
    )
    second = _quote(
        quotes,
        transport_provider_id=ODDSPAPI_PROVIDER_ID,
        price_provider_id=phase16_5.PINNACLE_ID,
        selection_id=phase16_5.HOME_SELECTION_ID,
    )
    timestamp = phase16_5.AS_OF - timedelta(seconds=30)
    first = replace(first, source_timestamp=timestamp, ingested_at=phase16_5.AS_OF)
    second = replace(
        second,
        decimal_price=first.decimal_price + Decimal("0.10"),
        source_timestamp=timestamp,
        ingested_at=phase16_5.AS_OF,
    )

    result = consolidate_quotes((first, second))

    assert result.quotes == ()
    assert result.conflict_count == 1
    assert result.equivalent_overlap_count == 0
    assert result.diagnostics[0].code is ConsolidationDiagnosticCode.MATERIAL_CONFLICT
    assert set(result.diagnostics[0].transport_provider_ids) == {
        THE_ODDS_API_PROVIDER_ID,
        ODDSPAPI_PROVIDER_ID,
    }


def test_equal_time_equivalent_real_observations_consolidate_deterministically() -> None:
    _registry, _observations, quotes = _real_quotes()
    first = _quote(
        quotes,
        transport_provider_id=THE_ODDS_API_PROVIDER_ID,
        price_provider_id=phase16_5.PINNACLE_ID,
        selection_id=phase16_5.DRAW_SELECTION_ID,
    )
    second = _quote(
        quotes,
        transport_provider_id=ODDSPAPI_PROVIDER_ID,
        price_provider_id=phase16_5.PINNACLE_ID,
        selection_id=phase16_5.DRAW_SELECTION_ID,
    )
    timestamp = phase16_5.AS_OF - timedelta(seconds=30)
    first = replace(first, source_timestamp=timestamp, ingested_at=phase16_5.AS_OF)
    second = replace(
        second,
        decimal_price=first.decimal_price,
        source_timestamp=timestamp,
        ingested_at=phase16_5.AS_OF,
    )

    forward = consolidate_quotes((first, second))
    reverse = consolidate_quotes((second, first))

    assert forward.quotes == reverse.quotes
    assert len(forward.quotes) == 1
    assert forward.equivalent_overlap_count == 1
    diagnostic = forward.diagnostics[0]
    assert diagnostic.code is ConsolidationDiagnosticCode.EQUIVALENT_OVERLAP
    assert set(diagnostic.transport_provider_ids) == {
        THE_ODDS_API_PROVIDER_ID,
        ODDSPAPI_PROVIDER_ID,
    }
    assert set(diagnostic.quote_ids) == {first.id.value, second.id.value}


def test_unmatched_real_source_cannot_enter_the_other_sources_market_book() -> None:
    registry, observations, quotes = _real_quotes()
    the_odds, _oddspapi = observations
    valid_hooks, _decision = _hooks_for_observation(the_odds, registry)
    assert isinstance(valid_hooks.base, StaticCanonicalIdHooks)

    reversed_event = replace(
        the_odds.event,
        participants=tuple(reversed(the_odds.event.participants)),
    )
    prepared = prepare_event_evidence(
        provider_id=the_odds.adapter.provider.id,
        event=reversed_event,
        competition=the_odds.competition,
        competition_normalizer=phase16_5._competition_normalizer(),
        participant_normalizer=phase16_5._participant_normalizer(),
        participant_kind=ParticipantKind.TEAM,
        order_policy=ParticipantOrderPolicy.ORDERED,
    )
    assert prepared.evidence is not None
    rejected = EventMatcher(registry).match(prepared.evidence)
    assert rejected.status is EventMatchStatus.REJECTED

    rejected_hooks = MatchedCanonicalIdHooks(
        base=valid_hooks.base,
        event_decisions={reversed_event.external_id: rejected},
    )
    normalized = normalize_source_snapshot(
        provider=the_odds.adapter.provider,
        hooks=rejected_hooks,
        event=reversed_event,
        snapshot=the_odds.snapshot,
        registry=registry,
        as_of=phase16_5.AS_OF,
        freshness_window=phase16_5.FRESHNESS_WINDOW,
    )
    assert normalized.quotes == ()

    healthy_quotes = quotes[ODDSPAPI_PROVIDER_ID]
    book = _book(registry, healthy_quotes)
    assert {
        outcome.quote.transport_provider_id for outcome in book.outcomes
    } == {ODDSPAPI_PROVIDER_ID}


def test_suspended_real_source_observation_is_invalidated_independently() -> None:
    _registry, _observations, quotes = _real_quotes()
    the_odds = _quote(
        quotes,
        transport_provider_id=THE_ODDS_API_PROVIDER_ID,
        price_provider_id=phase16_5.PINNACLE_ID,
        selection_id=phase16_5.HOME_SELECTION_ID,
    )
    oddspapi = _quote(
        quotes,
        transport_provider_id=ODDSPAPI_PROVIDER_ID,
        price_provider_id=phase16_5.PINNACLE_ID,
        selection_id=phase16_5.HOME_SELECTION_ID,
    )
    store = _store((the_odds, oddspapi))
    suspended = replace(
        the_odds,
        status=QuoteStatus.SUSPENDED,
        source_timestamp=phase16_5.AS_OF,
        ingested_at=phase16_5.AS_OF,
    )

    update = store.apply((suspended,), observed_at=phase16_5.AS_OF)

    assert update.updated_count == 1
    assert store.fresh_observations(as_of=phase16_5.AS_OF) == (oddspapi,)
    assert store.fresh_quotes(as_of=phase16_5.AS_OF) == (oddspapi,)


def test_provider_policy_targets_price_origins_not_transport_sources() -> None:
    registry, _observations, quotes = _real_quotes()
    consolidated = _store(_flatten(quotes)).fresh_quotes(as_of=phase16_5.AS_OF)

    unrestricted = _book(registry, consolidated)
    without_bet365 = _book(
        registry,
        consolidated,
        provider_policy=ProviderBookPolicy(excluded_provider_ids=(BET365_ID,)),
    )
    excluding_transport_id = _book(
        registry,
        consolidated,
        provider_policy=ProviderBookPolicy(
            excluded_provider_ids=(THE_ODDS_API_PROVIDER_ID,)
        ),
    )

    unrestricted_by_selection = {
        outcome.selection.id: outcome.quote.provider_id for outcome in unrestricted.outcomes
    }
    without_bet365_by_selection = {
        outcome.selection.id: outcome.quote.provider_id for outcome in without_bet365.outcomes
    }
    transport_filtered_by_selection = {
        outcome.selection.id: outcome.quote.provider_id
        for outcome in excluding_transport_id.outcomes
    }

    assert unrestricted_by_selection[phase16_5.HOME_SELECTION_ID] == BET365_ID
    assert without_bet365_by_selection[phase16_5.HOME_SELECTION_ID] == phase16_5.PINNACLE_ID
    assert transport_filtered_by_selection == unrestricted_by_selection


def test_persisted_real_opportunity_preserves_price_and_transport_provenance(
    tmp_path: Path,
) -> None:
    registry, _observations, quotes = _real_quotes()
    consolidated = _store(_flatten(quotes)).fresh_quotes(as_of=phase16_5.AS_OF)
    book = _book(registry, consolidated)
    selected_quotes = tuple(outcome.quote for outcome in book.outcomes)
    evaluation = evaluate_market(selected_quotes, book.expected_selection_ids)
    assert evaluation.is_arbitrage

    opportunity = build_opportunity(
        evaluation,
        opportunity_id=OpportunityId("opportunity:phase16-6:real-coexistence"),
        detected_at=phase16_5.AS_OF,
    )
    store = SqliteAuditStore(tmp_path / "phase16-6.db")
    store.migrate()
    store.persist_opportunity(opportunity, evaluation.quotes)

    restored = store.reconstruct_opportunity(opportunity.id.value)

    assert tuple(quote.provider_id for quote in restored.quotes) == tuple(
        quote.provider_id for quote in evaluation.quotes
    )
    assert tuple(quote.transport_provider_id for quote in restored.quotes) == tuple(
        quote.transport_provider_id for quote in evaluation.quotes
    )
    assert {quote.transport_provider_id for quote in restored.quotes} == {
        THE_ODDS_API_PROVIDER_ID,
        ODDSPAPI_PROVIDER_ID,
    }
    provenance = {
        quote.provider_id: quote.transport_provider_id for quote in restored.quotes
    }
    assert provenance[BET365_ID] == THE_ODDS_API_PROVIDER_ID
    assert provenance[BETFAIR_ID] == ODDSPAPI_PROVIDER_ID
