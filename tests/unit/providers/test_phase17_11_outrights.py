"""Phase 17.11 provider feasibility gates for broader outright markets."""

from __future__ import annotations

import asyncio

from arbiscan.domain import Sport
from arbiscan.providers import ProviderError, ProviderErrorKind
from arbiscan.providers.oddspapi import OddsPapiConfig, OddsPapiProvider
from arbiscan.providers.the_odds_api import TheOddsApiConfig, TheOddsApiProvider
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as TheOddsApiFixtureTransport

EVENT_ID = "id1000001761301153"


def test_the_odds_api_preserves_outright_flag_and_rejects_binary_event_parser() -> None:
    transport = TheOddsApiFixtureTransport(
        fixture_overrides={"sports": "sports_phase17_11_outright.json"}
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture"),
        transport=transport,
    )

    competitions = asyncio.run(provider.discover_competitions(Sport.FOOTBALL))
    assert tuple(value.external_id for value in competitions) == (
        "soccer_epl",
        "soccer_uefa_champions_league_winner",
    )

    try:
        asyncio.run(provider.discover_events("soccer_uefa_champions_league_winner"))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.UNSUPPORTED
        assert "multi-participant parser" in str(error)
        assert "complete candidate-set proof" in str(error)
    else:
        raise AssertionError("outright competition must not enter binary event parsing")


def test_oddspapi_unverified_tournament_winner_catalog_family_is_not_promoted() -> None:
    async def scenario() -> None:
        transport = OddsPapiFixtureTransport(
            fixture_overrides={
                "/markets": "markets_phase17_11_outright_unverified.json",
            }
        )
        provider = OddsPapiProvider(
            config=OddsPapiConfig(api_key="fixture"),
            transport=transport,
        )

        competitions = await provider.discover_competitions(Sport.FOOTBALL)
        assert tuple(value.external_id for value in competitions) == ("17",)
        events = await provider.discover_events("17")
        assert tuple(value.external_id for value in events) == (EVENT_ID,)

        snapshot = await provider.fetch_odds(EVENT_ID)
        assert snapshot is not None
        assert snapshot.markets == ()

    asyncio.run(scenario())
