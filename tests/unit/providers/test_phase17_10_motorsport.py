"""Phase 17.10 provider feasibility gates for motorsport/F1 semantics."""

from __future__ import annotations

import asyncio

from arbiscan.domain import Sport
from arbiscan.providers import ProviderError, ProviderErrorKind
from arbiscan.providers.oddspapi import OddsPapiConfig, OddsPapiProvider
from arbiscan.providers.the_odds_api import TheOddsApiConfig, TheOddsApiProvider
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as TheOddsApiFixtureTransport


def test_the_odds_api_discovers_motorsport_group_but_rejects_binary_event_promotion() -> None:
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture"),
        transport=TheOddsApiFixtureTransport(
            fixture_overrides={"sports": "sports_phase17_10_motorsport.json"}
        ),
    )

    sports = asyncio.run(provider.supported_sports())
    competitions = asyncio.run(provider.discover_competitions(Sport.MOTORSPORT))

    assert Sport.MOTORSPORT in sports
    assert tuple(value.external_id for value in competitions) == (
        "fixture_formula1_outright",
    )

    try:
        asyncio.run(provider.discover_events("fixture_formula1_outright"))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.UNSUPPORTED
        assert "multi-participant parser" in str(error)
    else:
        raise AssertionError("motorsport outright event must not use binary home/away identity")


def test_oddspapi_advertised_motorsport_record_remains_unmapped_without_verified_identifier() -> None:
    provider = OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture"),
        transport=OddsPapiFixtureTransport(
            fixture_overrides={
                "/sports": "sports_phase17_10_motorsport_unverified.json",
            }
        ),
    )

    sports = asyncio.run(provider.supported_sports())

    assert Sport.MOTORSPORT not in sports
    assert sports == (Sport.BASKETBALL, Sport.FOOTBALL, Sport.TENNIS)

    try:
        asyncio.run(provider.discover_competitions(Sport.MOTORSPORT))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.UNSUPPORTED
    else:
        raise AssertionError(
            "OddsPapi motorsport must remain unmapped until an exact live slug/id is verified"
        )
