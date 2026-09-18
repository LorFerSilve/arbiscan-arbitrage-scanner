"""Phase 17.12 regression: ordinary aggregator prices must not gain exchange semantics."""

from __future__ import annotations

import asyncio

from arbiscan.domain import ProviderKind, Sport
from arbiscan.providers.oddspapi import OddsPapiConfig, OddsPapiProvider
from tests.support.oddspapi import FixtureHttpTransport


def test_betfair_slug_from_current_aggregator_remains_bookmaker_price_origin() -> None:
    async def scenario() -> None:
        transport = FixtureHttpTransport(
            fixture_overrides={
                "/tournaments": "tournaments_basketball_phase17_9.json",
                "/fixtures": "fixtures_tournament_132_phase17_9.json",
                "/markets": "markets_phase17_9_basketball.json",
                "/odds": "odds_fixture_phase17_9_basketball.json",
            }
        )
        provider = OddsPapiProvider(
            config=OddsPapiConfig(api_key="fixture"),
            transport=transport,
        )
        competitions = await provider.discover_competitions(Sport.BASKETBALL)
        assert tuple(value.external_id for value in competitions) == ("132",)
        events = await provider.discover_events("132")
        snapshot = await provider.fetch_odds(events[0].external_id)

        assert snapshot is not None
        betfair_origins = {
            market.price_provider
            for market in snapshot.markets
            if market.price_provider is not None
            and market.price_provider.id.value.endswith(":betfair")
        }
        assert betfair_origins
        assert {provider.kind for provider in betfair_origins} == {ProviderKind.BOOKMAKER}

    asyncio.run(scenario())
