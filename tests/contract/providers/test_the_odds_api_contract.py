"""The first real provider must satisfy the reusable Phase 4 contract."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from arbiscan.domain import ProviderId, Sport
from arbiscan.providers.the_odds_api import TheOddsApiConfig, TheOddsApiProvider
from tests.contract.providers.conformance import ProviderContractCase, assert_provider_conformance
from tests.support.the_odds_api import FixtureHttpTransport

NOW = datetime(2026, 9, 20, 11, 5, tzinfo=UTC)


def test_the_odds_api_provider_passes_shared_contract_from_recorded_fixtures() -> None:
    async def scenario() -> None:
        provider = TheOddsApiProvider(
            config=TheOddsApiConfig(api_key="fixture"),
            transport=FixtureHttpTransport(),
            clock=lambda: NOW,
        )
        events = await provider.discover_events("soccer_epl")
        expected = await provider.fetch_odds(events[0].external_id)
        assert expected is not None

        await assert_provider_conformance(
            ProviderContractCase(
                adapter=provider,
                expected_provider_id=ProviderId("provider:the-odds-api"),
                sport=Sport.FOOTBALL,
                competition_external_id="soccer_epl",
                event_external_id="epl-arsenal-chelsea-20260920",
                expected_snapshot=expected,
                expect_streaming=False,
            )
        )

    asyncio.run(scenario())
