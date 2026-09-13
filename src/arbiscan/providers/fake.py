"""Deterministic in-memory provider used to prove the Phase 4 adapter contract."""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from arbiscan.domain import Provider, ProviderKind, Sport
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.errors import (
    ProviderContractError,
    ProviderError,
    ProviderErrorKind,
)
from arbiscan.providers.models import (
    CanonicalIdHooks,
    OddsSnapshot,
    ProviderCapabilities,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthState,
    ProviderOperation,
    RateLimitSnapshot,
    SourceCompetition,
    SourceEvent,
)


@dataclass(frozen=True, slots=True)
class FakeProviderFixtures:
    """Immutable source records returned by the deterministic fake adapter."""

    sports: tuple[Sport, ...]
    competitions: tuple[SourceCompetition, ...] = field(default_factory=tuple)
    events: tuple[SourceEvent, ...] = field(default_factory=tuple)
    odds_snapshots: tuple[OddsSnapshot, ...] = field(default_factory=tuple)
    stream_snapshots: tuple[OddsSnapshot, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        sports = tuple(self.sports)
        competitions = tuple(self.competitions)
        events = tuple(self.events)
        odds_snapshots = tuple(self.odds_snapshots)
        stream_snapshots = tuple(self.stream_snapshots)
        if any(not isinstance(sport, Sport) for sport in sports):
            raise ProviderContractError("fake provider sports must contain Sport values")
        if len(set(sports)) != len(sports):
            raise ProviderContractError("fake provider sports must be unique")
        if any(not isinstance(value, SourceCompetition) for value in competitions):
            raise ProviderContractError("fake competitions must be SourceCompetition values")
        if any(not isinstance(value, SourceEvent) for value in events):
            raise ProviderContractError("fake events must be SourceEvent values")
        if any(not isinstance(value, OddsSnapshot) for value in odds_snapshots):
            raise ProviderContractError("fake odds must be OddsSnapshot values")
        if any(not isinstance(value, OddsSnapshot) for value in stream_snapshots):
            raise ProviderContractError("fake stream values must be OddsSnapshot values")
        object.__setattr__(self, "sports", sports)
        object.__setattr__(self, "competitions", competitions)
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "odds_snapshots", odds_snapshots)
        object.__setattr__(self, "stream_snapshots", stream_snapshots)


class FakeProvider(ProviderAdapter):
    """In-memory contract implementation with deterministic scripted failures and delays."""

    def __init__(
        self,
        *,
        provider: Provider,
        fixtures: FakeProviderFixtures,
        health: ProviderHealth | None = None,
        rate_limit: RateLimitSnapshot | None = None,
        canonical_id_hooks: CanonicalIdHooks | None = None,
        supports_streaming: bool = False,
        scripted_failures: Mapping[ProviderOperation, tuple[ProviderError, ...]] | None = None,
        operation_delays: Mapping[ProviderOperation, float] | None = None,
    ) -> None:
        if not isinstance(provider, Provider):
            raise ProviderContractError("fake provider metadata must be Provider")
        if provider.kind is not ProviderKind.SYNTHETIC:
            raise ProviderContractError("FakeProvider requires ProviderKind.SYNTHETIC")
        if not isinstance(fixtures, FakeProviderFixtures):
            raise ProviderContractError("fixtures must be FakeProviderFixtures")
        if type(supports_streaming) is not bool:
            raise ProviderContractError("supports_streaming must be bool")
        if fixtures.stream_snapshots and not supports_streaming:
            raise ProviderContractError(
                "stream fixtures require supports_streaming=True"
            )

        self._provider = provider
        self._fixtures = fixtures
        self._health = health or ProviderHealth(
            provider_id=provider.id,
            state=ProviderHealthState.HEALTHY,
            checked_at=datetime(1970, 1, 1, tzinfo=UTC),
        )
        self._rate_limit = rate_limit
        self._canonical_id_hooks = canonical_id_hooks
        self._failures: dict[ProviderOperation, deque[ProviderError]] = defaultdict(deque)
        self._delays: dict[ProviderOperation, float] = {}

        self._validate_fixture_graph()
        self._load_failures(scripted_failures or {})
        self._load_delays(operation_delays or {})

        capabilities = {
            ProviderCapability.SPORT_DISCOVERY,
            ProviderCapability.COMPETITION_DISCOVERY,
            ProviderCapability.EVENT_DISCOVERY,
            ProviderCapability.ODDS_SNAPSHOTS,
            ProviderCapability.HEALTH,
        }
        if rate_limit is not None:
            capabilities.add(ProviderCapability.RATE_LIMIT_METADATA)
        if canonical_id_hooks is not None:
            capabilities.add(ProviderCapability.CANONICAL_ID_HINTS)
        if supports_streaming:
            capabilities.add(ProviderCapability.ODDS_STREAMING)
        self._capabilities = ProviderCapabilities(frozenset(capabilities))

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    @property
    def canonical_id_hooks(self) -> CanonicalIdHooks | None:
        return self._canonical_id_hooks

    async def supported_sports(self) -> tuple[Sport, ...]:
        await self._before(ProviderOperation.SUPPORTED_SPORTS)
        return tuple(sorted(self._fixtures.sports, key=lambda sport: sport.value))

    async def discover_competitions(self, sport: Sport) -> tuple[SourceCompetition, ...]:
        await self._before(ProviderOperation.DISCOVER_COMPETITIONS)
        if not isinstance(sport, Sport):
            raise self._invalid_request(
                ProviderOperation.DISCOVER_COMPETITIONS,
                "sport must be Sport",
            )
        return tuple(
            sorted(
                (item for item in self._fixtures.competitions if item.sport is sport),
                key=lambda item: item.external_id,
            )
        )

    async def discover_events(
        self,
        competition_external_id: str,
        *,
        starts_after: datetime | None = None,
        starts_before: datetime | None = None,
    ) -> tuple[SourceEvent, ...]:
        await self._before(ProviderOperation.DISCOVER_EVENTS)
        competition_id = self._request_text(
            competition_external_id,
            ProviderOperation.DISCOVER_EVENTS,
            "competition_external_id",
        )
        after = self._query_time(starts_after, ProviderOperation.DISCOVER_EVENTS, "starts_after")
        before = self._query_time(
            starts_before,
            ProviderOperation.DISCOVER_EVENTS,
            "starts_before",
        )
        if after is not None and before is not None and after > before:
            raise self._invalid_request(
                ProviderOperation.DISCOVER_EVENTS,
                "starts_after cannot be later than starts_before",
            )

        events = (
            event
            for event in self._fixtures.events
            if event.competition_external_id == competition_id
            and (after is None or event.scheduled_start >= after)
            and (before is None or event.scheduled_start <= before)
        )
        return tuple(sorted(events, key=lambda event: (event.scheduled_start, event.external_id)))

    async def fetch_odds(self, external_event_id: str) -> OddsSnapshot | None:
        await self._before(ProviderOperation.FETCH_ODDS)
        event_id = self._request_text(
            external_event_id,
            ProviderOperation.FETCH_ODDS,
            "external_event_id",
        )
        for snapshot in self._fixtures.odds_snapshots:
            if snapshot.external_event_id == event_id:
                return snapshot
        return None

    def stream_odds(self, external_event_ids: tuple[str, ...]) -> AsyncIterator[OddsSnapshot]:
        return self._stream_odds(external_event_ids)

    async def _stream_odds(
        self,
        external_event_ids: tuple[str, ...],
    ) -> AsyncIterator[OddsSnapshot]:
        await self._before(ProviderOperation.STREAM_ODDS)
        if not self.capabilities.supports(ProviderCapability.ODDS_STREAMING):
            raise ProviderError(
                provider_id=self.provider.id,
                operation=ProviderOperation.STREAM_ODDS.value,
                kind=ProviderErrorKind.UNSUPPORTED,
                message="fake provider does not declare odds streaming",
                retryable=False,
            )
        requested = tuple(
            self._request_text(
                value,
                ProviderOperation.STREAM_ODDS,
                "external_event_ids[]",
            )
            for value in external_event_ids
        )
        if not requested:
            raise self._invalid_request(
                ProviderOperation.STREAM_ODDS,
                "stream_odds requires at least one event ID",
            )
        requested_set = set(requested)
        for snapshot in self._fixtures.stream_snapshots:
            if snapshot.external_event_id in requested_set:
                yield snapshot

    async def health(self) -> ProviderHealth:
        await self._before(ProviderOperation.HEALTH)
        return self._health

    async def rate_limit(self) -> RateLimitSnapshot | None:
        await self._before(ProviderOperation.RATE_LIMIT)
        return self._rate_limit

    async def _before(self, operation: ProviderOperation) -> None:
        delay = self._delays.get(operation, 0.0)
        if delay > 0:
            await asyncio.sleep(delay)
        queue = self._failures.get(operation)
        if queue:
            raise queue.popleft()

    def _load_failures(
        self,
        scripted_failures: Mapping[ProviderOperation, tuple[ProviderError, ...]],
    ) -> None:
        for operation, errors in scripted_failures.items():
            if not isinstance(operation, ProviderOperation):
                raise ProviderContractError("scripted failure key must be ProviderOperation")
            for error in errors:
                if not isinstance(error, ProviderError):
                    raise ProviderContractError("scripted failures must be ProviderError values")
                if error.provider_id != self.provider.id:
                    raise ProviderContractError(
                        "scripted failure provider_id must match the fake provider"
                    )
                self._failures[operation].append(error)

    def _load_delays(self, delays: Mapping[ProviderOperation, float]) -> None:
        for operation, delay in delays.items():
            if not isinstance(operation, ProviderOperation):
                raise ProviderContractError("operation delay key must be ProviderOperation")
            if isinstance(delay, bool) or not isinstance(delay, (int, float)):
                raise ProviderContractError("operation delay must be numeric")
            if not math.isfinite(float(delay)) or delay < 0:
                raise ProviderContractError("operation delay must be finite and non-negative")
            self._delays[operation] = float(delay)

    def _validate_fixture_graph(self) -> None:
        competition_ids = {competition.external_id for competition in self._fixtures.competitions}
        if len(competition_ids) != len(self._fixtures.competitions):
            raise ProviderContractError("fake competition external IDs must be unique")
        if any(
            competition.sport not in self._fixtures.sports
            for competition in self._fixtures.competitions
        ):
            raise ProviderContractError("fake competition sport must be declared by the provider")

        event_ids = {event.external_id for event in self._fixtures.events}
        if len(event_ids) != len(self._fixtures.events):
            raise ProviderContractError("fake event external IDs must be unique")
        for event in self._fixtures.events:
            if event.competition_external_id not in competition_ids:
                raise ProviderContractError("fake event references an unknown competition")
            competition = next(
                item
                for item in self._fixtures.competitions
                if item.external_id == event.competition_external_id
            )
            if event.sport is not competition.sport:
                raise ProviderContractError("fake event sport must match its competition")

        snapshot_ids: set[str] = set()
        for snapshot in self._fixtures.odds_snapshots:
            if snapshot.provider_id != self.provider.id:
                raise ProviderContractError("fake odds provider_id must match provider metadata")
            if snapshot.external_event_id not in event_ids:
                raise ProviderContractError("fake odds reference an unknown event")
            if snapshot.external_event_id in snapshot_ids:
                raise ProviderContractError("fake provider allows one odds snapshot per event")
            snapshot_ids.add(snapshot.external_event_id)
        for snapshot in self._fixtures.stream_snapshots:
            if snapshot.provider_id != self.provider.id:
                raise ProviderContractError("fake stream provider_id must match provider metadata")
            if snapshot.external_event_id not in event_ids:
                raise ProviderContractError("fake stream odds reference an unknown event")

        if self._health.provider_id != self.provider.id:
            raise ProviderContractError("fake health provider_id must match provider metadata")
        if self._rate_limit is not None and self._rate_limit.provider_id != self.provider.id:
            raise ProviderContractError("fake rate-limit provider_id must match provider metadata")

    def _request_text(
        self,
        value: object,
        operation: ProviderOperation,
        field_name: str,
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            raise self._invalid_request(operation, f"{field_name} must be non-empty text")
        return value.strip()

    def _query_time(
        self,
        value: datetime | None,
        operation: ProviderOperation,
        field_name: str,
    ) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise self._invalid_request(operation, f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)

    def _invalid_request(self, operation: ProviderOperation, message: str) -> ProviderError:
        return ProviderError(
            provider_id=self.provider.id,
            operation=operation.value,
            kind=ProviderErrorKind.INVALID_REQUEST,
            message=message,
            retryable=False,
        )
