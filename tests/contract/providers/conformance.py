"""Reusable provider conformance assertions for every adapter implementation."""

from __future__ import annotations

from dataclasses import dataclass

from arbiscan.domain import ProviderId, Sport
from arbiscan.providers import (
    OddsSnapshot,
    ProviderAdapter,
    ProviderCapability,
    ProviderError,
    ProviderErrorKind,
)


@dataclass(frozen=True, slots=True)
class ProviderContractCase:
    adapter: ProviderAdapter
    expected_provider_id: ProviderId
    sport: Sport
    competition_external_id: str
    event_external_id: str
    expected_snapshot: OddsSnapshot
    expect_streaming: bool


async def assert_provider_conformance(case: ProviderContractCase) -> None:
    """Exercise the shared behavior required from any provider adapter."""
    adapter = case.adapter
    assert adapter.provider.id == case.expected_provider_id

    sports = await adapter.supported_sports()
    assert case.sport in sports
    assert sports == await adapter.supported_sports()

    competitions = await adapter.discover_competitions(case.sport)
    assert any(
        competition.external_id == case.competition_external_id for competition in competitions
    )
    assert competitions == await adapter.discover_competitions(case.sport)

    events = await adapter.discover_events(case.competition_external_id)
    assert any(event.external_id == case.event_external_id for event in events)
    assert events == await adapter.discover_events(case.competition_external_id)

    snapshot = await adapter.fetch_odds(case.event_external_id)
    assert snapshot == case.expected_snapshot
    assert snapshot == await adapter.fetch_odds(case.event_external_id)

    health = await adapter.health()
    assert health.provider_id == case.expected_provider_id
    rate_limit = await adapter.rate_limit()
    if rate_limit is not None:
        assert rate_limit.provider_id == case.expected_provider_id

    if case.expect_streaming:
        assert adapter.capabilities.supports(ProviderCapability.ODDS_STREAMING)
        streamed = [update async for update in adapter.stream_odds((case.event_external_id,))]
        assert all(update.provider_id == case.expected_provider_id for update in streamed)
    else:
        assert not adapter.capabilities.supports(ProviderCapability.ODDS_STREAMING)
        try:
            _ = [update async for update in adapter.stream_odds((case.event_external_id,))]
        except ProviderError as exc:
            assert exc.kind is ProviderErrorKind.UNSUPPORTED
        else:
            raise AssertionError("non-streaming provider must fail with ProviderError.UNSUPPORTED")
