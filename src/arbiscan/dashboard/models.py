"""Transport-neutral dashboard and alert contracts for Phase 15."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from arbiscan.lifecycle import LifecycleState


@dataclass(frozen=True, slots=True)
class DashboardLeg:
    """One backend-calculated leg displayed without recomputation."""

    selection_id: str
    provider_id: str
    decimal_price: Decimal
    stake: Decimal
    quote_observed_at: str

    def __post_init__(self) -> None:
        if not self.decimal_price.is_finite() or not self.stake.is_finite():
            raise ValueError("dashboard leg numeric values must be finite")


@dataclass(frozen=True, slots=True)
class DashboardOpportunity:
    """Complete backend projection required by the user-facing dashboard."""

    opportunity_id: str
    event_id: str
    sport: str
    competition: str
    market_id: str
    state: LifecycleState
    detected_at: str
    age_seconds: Decimal
    roi: Decimal
    guaranteed_payout: Decimal
    guaranteed_profit: Decimal
    legs: tuple[DashboardLeg, ...]
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        numeric_values = (
            self.age_seconds,
            self.roi,
            self.guaranteed_payout,
            self.guaranteed_profit,
        )
        if any(not value.is_finite() for value in numeric_values):
            raise ValueError("dashboard opportunity numeric values must be finite")
        if self.age_seconds < 0:
            raise ValueError("age_seconds cannot be negative")
        if not self.legs:
            raise ValueError("dashboard opportunity requires at least one leg")


@dataclass(frozen=True, slots=True)
class DashboardFilter:
    sport: str | None = None
    competition: str | None = None
    provider_id: str | None = None
    minimum_roi: Decimal | None = None
    minimum_profit: Decimal | None = None
    include_inactive: bool = False


class AlertKind(StrEnum):
    CREATED = "created"
    CHANGED = "changed"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class OpportunityAlert:
    opportunity_id: str
    kind: AlertKind
    state: LifecycleState
    fingerprint: str
