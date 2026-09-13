"""Strongly typed identifiers used by the canonical domain model."""

from __future__ import annotations

from dataclasses import dataclass

from arbiscan.domain.validation import normalize_text


@dataclass(frozen=True, slots=True)
class CanonicalId:
    """Validated opaque identifier base class.

    IDs are deliberately opaque: consumers may compare and serialize them but must
    not infer domain meaning from their textual representation.
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            normalize_text(self.value, field=type(self).__name__, max_length=200),
        )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CompetitionId(CanonicalId):
    """Canonical competition identifier."""


@dataclass(frozen=True, slots=True)
class ParticipantId(CanonicalId):
    """Canonical participant identifier."""


@dataclass(frozen=True, slots=True)
class EventId(CanonicalId):
    """Canonical sporting-event identifier."""


@dataclass(frozen=True, slots=True)
class MarketId(CanonicalId):
    """Canonical market identifier."""


@dataclass(frozen=True, slots=True)
class SelectionId(CanonicalId):
    """Canonical market-selection identifier."""


@dataclass(frozen=True, slots=True)
class QuoteId(CanonicalId):
    """Canonical odds-quote identifier."""


@dataclass(frozen=True, slots=True)
class ProviderId(CanonicalId):
    """Canonical provider identifier."""


@dataclass(frozen=True, slots=True)
class OpportunityId(CanonicalId):
    """Canonical arbitrage-opportunity identifier."""


@dataclass(frozen=True, slots=True)
class StakePlanId(CanonicalId):
    """Canonical stake-plan identifier."""
