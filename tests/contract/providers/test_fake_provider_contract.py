"""The deterministic fake provider must satisfy the reusable provider contract suite."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from arbiscan.domain import Provider, ProviderId, ProviderKind, Sport
from arbiscan.providers import (
    FakeProvider,
    FakeProviderFixtures,
    OddsSnapshot,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthState,
    RateLimitSnapshot,
    SourceCompetition,
    SourceEvent,
    SourceMarket,
    SourceOddsFormat,
    SourceParticipant,
    SourceSelectionQuote,
)
from tests.contract.providers.conformance import (
    ProviderContractCase,
    assert_provider_conformance,
)

NOW = datetime(2026, 9, 13, 10, 0, tzinfo=UTC)
PROVIDER_ID = ProviderId("provider:fake")


def build_provider(
    *,
    streaming: bool,
    stream_has_update: bool = True,
) -> tuple[FakeProvider, OddsSnapshot]:
    provider = Provider(
        id=PROVIDER_ID,
        name="Deterministic Fake",
        kind=ProviderKind.SYNTHETIC,
    )
    competition = SourceCompetition(
        external_id="competition:epl",
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
        season="2026/27",
    )
    event = SourceEvent(
        external_id="event:arsenal-chelsea",
        sport=Sport.FOOTBALL,
        competition_external_id=competition.external_id,
        participants=(
            SourceParticipant(external_id="team:arsenal", name="Arsenal", role="home"),
            SourceParticipant(external_id="team:chelsea", name="Chelsea", role="away"),
        ),
        scheduled_start=datetime(2026, 9, 20, 16, 30, tzinfo=UTC),
        source_status="scheduled",
    )
    market = SourceMarket(
        external_event_id=event.external_id,
        external_market_id="market:1x2",
        label="Full Time Result",
        selections=(
            SourceSelectionQuote(
                external_selection_id="selection:home",
                label="1",
                price="2.40",
                odds_format=SourceOddsFormat.DECIMAL,
            ),
            SourceSelectionQuote(
                external_selection_id="selection:draw",
                label="X",
                price="3.50",
                odds_format=SourceOddsFormat.DECIMAL,
            ),
            SourceSelectionQuote(
                external_selection_id="selection:away",
                label="2",
                price="3.00",
                odds_format=SourceOddsFormat.DECIMAL,
            ),
        ),
    )
    snapshot = OddsSnapshot(
        provider_id=PROVIDER_ID,
        external_event_id=event.external_id,
        markets=(market,),
        source_timestamp=NOW,
        ingested_at=NOW,
        trace_id="trace:fake:1",
    )
    fixtures = FakeProviderFixtures(
        sports=(Sport.FOOTBALL, Sport.TENNIS),
        competitions=(competition,),
        events=(event,),
        odds_snapshots=(snapshot,),
        stream_snapshots=(snapshot,) if streaming and stream_has_update else (),
    )
    fake = FakeProvider(
        provider=provider,
        fixtures=fixtures,
        health=ProviderHealth(
            provider_id=PROVIDER_ID,
            state=ProviderHealthState.HEALTHY,
            checked_at=NOW,
        ),
        rate_limit=RateLimitSnapshot(
            provider_id=PROVIDER_ID,
            observed_at=NOW,
            limit=100,
            remaining=87,
        ),
        supports_streaming=streaming,
    )
    return fake, snapshot


def test_fake_provider_passes_shared_contract_without_streaming() -> None:
    provider, snapshot = build_provider(streaming=False)
    case = ProviderContractCase(
        adapter=provider,
        expected_provider_id=PROVIDER_ID,
        sport=Sport.FOOTBALL,
        competition_external_id="competition:epl",
        event_external_id="event:arsenal-chelsea",
        expected_snapshot=snapshot,
        expect_streaming=False,
    )
    asyncio.run(assert_provider_conformance(case))


def test_fake_provider_passes_shared_contract_with_streaming() -> None:
    provider, snapshot = build_provider(streaming=True)
    case = ProviderContractCase(
        adapter=provider,
        expected_provider_id=PROVIDER_ID,
        sport=Sport.FOOTBALL,
        competition_external_id="competition:epl",
        event_external_id="event:arsenal-chelsea",
        expected_snapshot=snapshot,
        expect_streaming=True,
    )
    asyncio.run(assert_provider_conformance(case))


def test_streaming_capability_can_be_supported_while_stream_is_quiet() -> None:
    provider, _snapshot = build_provider(streaming=True, stream_has_update=False)

    async def scenario() -> None:
        assert provider.capabilities.supports(ProviderCapability.ODDS_STREAMING)
        updates = [update async for update in provider.stream_odds(("event:arsenal-chelsea",))]
        assert updates == []

    asyncio.run(scenario())
