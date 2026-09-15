"""Canonical ID hook wrapper that only exposes Phase-8 matched event identities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from arbiscan.domain import CompetitionId, EventId, MarketId, SelectionId
from arbiscan.matching.models import EventMatchDecision, EventMatchStatus
from arbiscan.providers.models import (
    CanonicalIdHooks,
    SourceCompetition,
    SourceEvent,
    SourceMarket,
    SourceSelectionQuote,
)


@dataclass(frozen=True, slots=True)
class MatchedCanonicalIdHooks(CanonicalIdHooks):
    """Delegate non-event IDs while failing closed on unmatched event decisions."""

    base: CanonicalIdHooks
    event_decisions: Mapping[str, EventMatchDecision] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.base is None:
            raise ValueError("base canonical ID hooks are required")
        decisions = dict(self.event_decisions)
        for external_event_id, decision in decisions.items():
            if not isinstance(external_event_id, str) or not external_event_id.strip():
                raise ValueError("event_decisions keys must be non-empty source event IDs")
            if not isinstance(decision, EventMatchDecision):
                raise ValueError("event_decisions values must be EventMatchDecision values")
        object.__setattr__(self, "event_decisions", MappingProxyType(decisions))

    def competition_id(self, record: SourceCompetition) -> CompetitionId | None:
        return self.base.competition_id(record)

    def event_id(self, record: SourceEvent) -> EventId | None:
        decision = self.event_decisions.get(record.external_id)
        if decision is None or decision.status is not EventMatchStatus.MATCHED:
            return None
        return decision.matched_event_id

    def market_id(self, record: SourceMarket) -> MarketId | None:
        return self.base.market_id(record)

    def selection_id(
        self,
        market: SourceMarket,
        record: SourceSelectionQuote,
    ) -> SelectionId | None:
        return self.base.selection_id(market, record)
