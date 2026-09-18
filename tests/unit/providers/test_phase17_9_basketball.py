"""Phase 17.9 provider regressions for basketball market semantics."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.domain import Sport
from arbiscan.providers import ProviderError, ProviderErrorKind
from arbiscan.providers.oddspapi import OddsPapiConfig, OddsPapiProvider
from arbiscan.providers.the_odds_api import TheOddsApiConfig, TheOddsApiProvider
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as TheOddsApiFixtureTransport

NOW = datetime(2026, 9, 18, 13, 0, tzinfo=UTC)


def test_the_odds_api_basketball_featured_markets_preserve_lines_and_orientation() -> None:
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture", markets=("spreads", "totals")),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={
                "events": "events_basketball_nba_phase17_9.json",
                "odds": "odds_event_phase17_9_basketball.json",
            }
        ),
        clock=lambda: NOW,
    )

    competition = next(
        value
        for value in asyncio.run(provider.discover_competitions(Sport.BASKETBALL))
        if value.external_id == "basketball_nba"
    )
    event = asyncio.run(provider.discover_events(competition.external_id))[0]
    snapshot = asyncio.run(provider.fetch_odds(event.external_id))

    assert event.sport is Sport.BASKETBALL
    assert tuple(participant.name for participant in event.participants) == (
        "Boston Celtics",
        "New York Knicks",
    )
    assert snapshot is not None
    assert len(snapshot.markets) == 4

    totals = tuple(market for market in snapshot.markets if market.label.endswith(" totals"))
    spreads = tuple(market for market in snapshot.markets if market.label.endswith(" spreads"))
    assert len(totals) == 2
    assert len(spreads) == 2
    assert {market.line for market in totals} == {Decimal("215.5")}
    assert {market.line for market in spreads} == {Decimal("-3.5")}
    assert all(
        {selection.label: selection.handicap for selection in market.selections}
        == {"Boston Celtics": Decimal("-3.5"), "New York Knicks": Decimal("3.5")}
        for market in spreads
    )


def test_the_odds_api_period_specific_basketball_total_fails_closed() -> None:
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture", markets=("totals_q1",)),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={
                "events": "events_basketball_nba_phase17_9.json",
                "odds": "odds_event_phase17_9_basketball_quarter.json",
            }
        ),
        clock=lambda: NOW,
    )
    event = asyncio.run(provider.discover_events("basketball_nba"))[0]

    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "unsupported point semantics" in str(error)
    else:
        raise AssertionError("quarter totals must not be promoted to full-event totals")


def test_oddspapi_basketball_overtime_markets_preserve_lines_and_orientation() -> None:
    provider = OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture"),
        transport=OddsPapiFixtureTransport(
            fixture_overrides={
                "/tournaments": "tournaments_basketball_phase17_9.json",
                "/fixtures": "fixtures_tournament_132_phase17_9.json",
                "/markets": "markets_phase17_9_basketball.json",
                "/odds": "odds_fixture_phase17_9_basketball.json",
            }
        ),
        clock=lambda: NOW,
    )
    competition = asyncio.run(provider.discover_competitions(Sport.BASKETBALL))[0]
    event = asyncio.run(provider.discover_events(competition.external_id))[0]
    snapshot = asyncio.run(provider.fetch_odds(event.external_id))

    assert competition.external_id == "132"
    assert event.sport is Sport.BASKETBALL
    assert snapshot is not None
    assert len(snapshot.markets) == 8

    totals = tuple(
        market for market in snapshot.markets if "Over Under (incl. overtime)" in market.label
    )
    spreads = tuple(
        market for market in snapshot.markets if "Handicap (incl. overtime)" in market.label
    )
    assert len(totals) == 4
    assert len(spreads) == 4
    assert {market.line for market in totals} == {Decimal("215.5")}
    assert {market.line for market in spreads} == {Decimal("-3.5")}

    pinnacle_spreads = tuple(
        market
        for market in spreads
        if market.price_provider is not None
        and market.price_provider.id.value == "bookmaker:the-odds-api:pinnacle"
    )
    assert {
        market.selections[0].label: market.selections[0].handicap for market in pinnacle_spreads
    } == {"1": Decimal("-3.5"), "2": Decimal("3.5")}


def test_oddspapi_quarter_market_is_not_promoted_to_full_event() -> None:
    provider = OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture"),
        transport=OddsPapiFixtureTransport(
            fixture_overrides={
                "/tournaments": "tournaments_basketball_phase17_9.json",
                "/fixtures": "fixtures_tournament_132_phase17_9.json",
                "/markets": "markets_phase17_9_basketball.json",
                "/odds": "odds_fixture_phase17_9_basketball_quarter_only.json",
            }
        ),
        clock=lambda: NOW,
    )
    competition = asyncio.run(provider.discover_competitions(Sport.BASKETBALL))[0]
    event = asyncio.run(provider.discover_events(competition.external_id))[0]
    snapshot = asyncio.run(provider.fetch_odds(event.external_id))

    assert snapshot is not None
    assert snapshot.markets == ()
