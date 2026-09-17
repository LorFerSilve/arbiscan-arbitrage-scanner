"""OddsPapi must satisfy the reusable provider adapter contract offline."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from arbiscan.domain import Sport
from arbiscan.providers.oddspapi import ODDSPAPI_PROVIDER_ID, OddsPapiConfig, OddsPapiProvider
from tests.contract.providers.conformance import ProviderContractCase, assert_provider_conformance
from tests.support.oddspapi import FixtureHttpTransport

NOW = datetime(2026, 9, 17, 10, 30, tzinfo=UTC)
EVENT_ID = "id1000001761301153"


def test_oddspapi_provider_passes_shared_contract_from_synthetic_fixtures() -> None:
    async def scenario() -> None:
        provider = OddsPapiProvider(
            config=OddsPapiConfig(api_key="fixture-only"),
            transport=FixtureHttpTransport(),
            clock=lambda: NOW,
        )

        competitions = await provider.discover_competitions(Sport.FOOTBALL)
        assert tuple(value.external_id for value in competitions) == ("17",)
        events = await provider.discover_events("17")
        assert tuple(value.external_id for value in events) == (EVENT_ID,)
        expected = await provider.fetch_odds(EVENT_ID)
        assert expected is not None

        await assert_provider_conformance(
            ProviderContractCase(
                adapter=provider,
                expected_provider_id=ODDSPAPI_PROVIDER_ID,
                sport=Sport.FOOTBALL,
                competition_external_id="17",
                event_external_id=EVENT_ID,
                expected_snapshot=expected,
                expect_streaming=False,
            )
        )

    asyncio.run(scenario())
