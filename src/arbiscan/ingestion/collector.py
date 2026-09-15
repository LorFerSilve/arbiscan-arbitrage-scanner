"""Deterministic provider ingestion used by the network-free vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from functools import partial

from arbiscan.domain import Provider, ProviderId, Sport
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.errors import ProviderError, ProviderErrorKind
from arbiscan.providers.models import (
    CanonicalIdHooks,
    OddsSnapshot,
    ProviderOperation,
    SourceEvent,
)
from arbiscan.providers.resilience import ProviderCallPolicy, ProviderExecutor


@dataclass(frozen=True, slots=True)
class IngestedSnapshot:
    """One source event and its structurally validated odds snapshot."""

    provider: Provider
    canonical_id_hooks: CanonicalIdHooks | None
    event: SourceEvent
    snapshot: OddsSnapshot


@dataclass(frozen=True, slots=True)
class IngestionIssue:
    """Fail-closed diagnostic emitted when one provider operation fails."""

    provider_id: ProviderId
    operation: str
    kind: ProviderErrorKind
    detail: str
    external_event_id: str | None = None
    retry_after: timedelta | None = None


@dataclass(frozen=True, slots=True)
class IngestionBatch:
    """Deterministic ingestion output with provider failures isolated as diagnostics."""

    snapshots: tuple[IngestedSnapshot, ...]
    issues: tuple[IngestionIssue, ...]


def _issue(error: ProviderError, *, external_event_id: str | None = None) -> IngestionIssue:
    return IngestionIssue(
        provider_id=error.provider_id,
        operation=error.operation,
        kind=error.kind,
        detail=str(error),
        external_event_id=external_event_id,
        retry_after=error.retry_after,
    )


def _snapshot_ownership_issue(
    adapter: ProviderAdapter,
    event: SourceEvent,
    snapshot: OddsSnapshot,
) -> IngestionIssue | None:
    """Reject cached/misrouted responses before they can be attributed canonically."""
    if snapshot.provider_id != adapter.provider.id:
        return IngestionIssue(
            provider_id=adapter.provider.id,
            operation=ProviderOperation.FETCH_ODDS.value,
            kind=ProviderErrorKind.MALFORMED_RESPONSE,
            detail=(
                "odds snapshot provider_id does not match the adapter provider: "
                f"expected {adapter.provider.id.value!r}, got {snapshot.provider_id.value!r}"
            ),
            external_event_id=event.external_id,
        )
    if snapshot.external_event_id != event.external_id:
        return IngestionIssue(
            provider_id=adapter.provider.id,
            operation=ProviderOperation.FETCH_ODDS.value,
            kind=ProviderErrorKind.MALFORMED_RESPONSE,
            detail=(
                "odds snapshot external_event_id does not match the requested event: "
                f"expected {event.external_id!r}, got {snapshot.external_event_id!r}"
            ),
            external_event_id=event.external_id,
        )
    return None


async def collect_snapshots(
    adapters: tuple[ProviderAdapter, ...],
    sport: Sport,
    *,
    policy: ProviderCallPolicy | None = None,
) -> IngestionBatch:
    """Collect source snapshots while isolating partial provider outages."""
    snapshots: list[IngestedSnapshot] = []
    issues: list[IngestionIssue] = []

    for adapter in sorted(adapters, key=lambda value: value.provider.id.value):
        executor = ProviderExecutor(adapter, policy=policy)

        try:
            supported = await executor.run(
                ProviderOperation.SUPPORTED_SPORTS,
                adapter.supported_sports,
            )
        except ProviderError as error:
            issues.append(_issue(error))
            continue
        if sport not in supported:
            continue

        try:
            competitions = await executor.run(
                ProviderOperation.DISCOVER_COMPETITIONS,
                partial(adapter.discover_competitions, sport),
            )
        except ProviderError as error:
            issues.append(_issue(error))
            continue

        for competition in competitions:
            try:
                events = await executor.run(
                    ProviderOperation.DISCOVER_EVENTS,
                    partial(adapter.discover_events, competition.external_id),
                )
            except ProviderError as error:
                issues.append(_issue(error))
                continue

            for event in events:
                try:
                    snapshot = await executor.run(
                        ProviderOperation.FETCH_ODDS,
                        partial(adapter.fetch_odds, event.external_id),
                    )
                except ProviderError as error:
                    issues.append(_issue(error, external_event_id=event.external_id))
                    continue
                if snapshot is None:
                    continue

                ownership_issue = _snapshot_ownership_issue(adapter, event, snapshot)
                if ownership_issue is not None:
                    issues.append(ownership_issue)
                    continue

                snapshots.append(
                    IngestedSnapshot(
                        provider=adapter.provider,
                        canonical_id_hooks=adapter.canonical_id_hooks,
                        event=event,
                        snapshot=snapshot,
                    )
                )

    return IngestionBatch(
        snapshots=tuple(
            sorted(
                snapshots,
                key=lambda item: (
                    item.provider.id.value,
                    item.event.scheduled_start,
                    item.event.external_id,
                ),
            )
        ),
        issues=tuple(
            sorted(
                issues,
                key=lambda item: (
                    item.provider_id.value,
                    item.operation,
                    item.external_event_id or "",
                    item.kind.value,
                ),
            )
        ),
    )
