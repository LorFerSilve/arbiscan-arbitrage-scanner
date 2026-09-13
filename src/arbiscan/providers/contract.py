"""Async provider adapter contract used by all external odds integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from arbiscan.domain import Provider, Sport
from arbiscan.providers.models import (
    CanonicalIdHooks,
    OddsSnapshot,
    ProviderCapabilities,
    ProviderHealth,
    RateLimitSnapshot,
    SourceCompetition,
    SourceEvent,
)


class ProviderAdapter(ABC):
    """Strict async integration boundary for one odds-data source."""

    @property
    @abstractmethod
    def provider(self) -> Provider:
        """Return canonical metadata identifying the source."""

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Return explicit supported capabilities."""

    @property
    @abstractmethod
    def canonical_id_hooks(self) -> CanonicalIdHooks | None:
        """Return optional source-to-canonical identity hooks."""

    @abstractmethod
    async def supported_sports(self) -> tuple[Sport, ...]:
        """Return canonical sports for which this source can discover data."""

    @abstractmethod
    async def discover_competitions(self, sport: Sport) -> tuple[SourceCompetition, ...]:
        """Return structurally validated source competitions for one sport."""

    @abstractmethod
    async def discover_events(
        self,
        competition_external_id: str,
        *,
        starts_after: datetime | None = None,
        starts_before: datetime | None = None,
    ) -> tuple[SourceEvent, ...]:
        """Return validated provider events with optional temporal filtering."""

    @abstractmethod
    async def fetch_odds(self, external_event_id: str) -> OddsSnapshot | None:
        """Fetch one validated odds snapshot, or None when the event has no snapshot."""

    @abstractmethod
    def stream_odds(self, external_event_ids: tuple[str, ...]) -> AsyncIterator[OddsSnapshot]:
        """Return an async odds stream or raise a generic unsupported ProviderError."""

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Return provider health without exposing implementation-specific errors."""

    @abstractmethod
    async def rate_limit(self) -> RateLimitSnapshot | None:
        """Return latest rate-limit metadata when the provider exposes it."""
