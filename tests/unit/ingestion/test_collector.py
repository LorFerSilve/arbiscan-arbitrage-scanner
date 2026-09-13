"""Regression tests for provider snapshot ownership validation."""

import asyncio
from dataclasses import replace

from arbiscan.domain import ProviderId, Sport
from arbiscan.ingestion.collector import collect_snapshots
from arbiscan.providers import FakeProvider, OddsSnapshot, ProviderErrorKind
from arbiscan.providers.synthetic import build_phase5_synthetic_scenario


class _WrongProviderSnapshotFake(FakeProvider):
    async def fetch_odds(self, external_event_id: str) -> OddsSnapshot | None:
        snapshot = await super().fetch_odds(external_event_id)
        if snapshot is None:
            return None
        return replace(snapshot, provider_id=ProviderId("provider:misrouted"))


class _WrongEventSnapshotFake(FakeProvider):
    async def fetch_odds(self, external_event_id: str) -> OddsSnapshot | None:
        snapshot = await super().fetch_odds(external_event_id)
        if snapshot is None:
            return None
        wrong_event_id = "event:misrouted"
        markets = tuple(
            replace(market, external_event_id=wrong_event_id) for market in snapshot.markets
        )
        return replace(
            snapshot,
            external_event_id=wrong_event_id,
            markets=markets,
        )


def _clone_alpha(provider_type: type[FakeProvider]) -> FakeProvider:
    scenario = build_phase5_synthetic_scenario()
    alpha = scenario.adapters[0]
    return provider_type(
        provider=alpha.provider,
        fixtures=alpha._fixtures,
        canonical_id_hooks=alpha.canonical_id_hooks,
    )


def test_collector_rejects_snapshot_from_wrong_provider() -> None:
    provider = _clone_alpha(_WrongProviderSnapshotFake)
    result = asyncio.run(collect_snapshots((provider,), Sport.FOOTBALL))

    assert result.snapshots == ()
    assert len(result.issues) == 5
    assert all(issue.kind is ProviderErrorKind.MALFORMED_RESPONSE for issue in result.issues)
    assert all("provider_id" in issue.detail for issue in result.issues)


def test_collector_rejects_snapshot_for_wrong_event() -> None:
    provider = _clone_alpha(_WrongEventSnapshotFake)
    result = asyncio.run(collect_snapshots((provider,), Sport.FOOTBALL))

    assert result.snapshots == ()
    assert len(result.issues) == 5
    assert all(issue.kind is ProviderErrorKind.MALFORMED_RESPONSE for issue in result.issues)
    assert all("external_event_id" in issue.detail for issue in result.issues)
