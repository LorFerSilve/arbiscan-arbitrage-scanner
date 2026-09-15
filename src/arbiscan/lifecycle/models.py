"""Operational opportunity lifecycle models for Phase 12."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from arbiscan.arbitrage.models import CurrencyRoundingPolicy, StakeConstraint
from arbiscan.domain import StakePlan


class LifecycleState(StrEnum):
    """Operational state of a detected theoretical opportunity."""

    DETECTED = "detected"
    VALIDATED = "validated"
    ACTIONABLE = "actionable"
    STALE = "stale"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class LifecycleReason(StrEnum):
    """Machine-readable reason for the resulting lifecycle state."""

    ACTIONABLE = "actionable"
    STALE_QUOTES = "stale_quotes"
    MARKET_CLOSED = "market_closed"
    QUOTE_SET_CHANGED = "quote_set_changed"
    NO_LONGER_ARBITRAGE = "no_longer_arbitrage"
    ODDS_DRIFT_EXCEEDED = "odds_drift_exceeded"
    STAKE_CONSTRAINTS = "stake_constraints"
    MINIMUM_PROFIT = "minimum_profit"
    MINIMUM_ROI = "minimum_roi"
    MAXIMUM_EXPOSURE = "maximum_exposure"


def _decimal(value: object, *, field: str, minimum: Decimal = Decimal("0")) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")
    if value < minimum:
        raise ValueError(f"{field} cannot be below {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class ActionabilityPolicy:
    """User/configuration supplied constraints used for practical revalidation."""

    bankroll: Decimal
    rounding_policy: CurrencyRoundingPolicy
    stake_constraints: tuple[StakeConstraint, ...] = ()
    maximum_quote_age_seconds: Decimal = Decimal("30")
    maximum_exposure: Decimal | None = None
    minimum_guaranteed_profit: Decimal = Decimal("0")
    minimum_roi: Decimal = Decimal("0")
    maximum_margin_drift: Decimal | None = None
    commission_rate: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "stake_constraints", tuple(self.stake_constraints))
        _decimal(self.bankroll, field="bankroll", minimum=Decimal("0.0000000001"))
        if not isinstance(self.rounding_policy, CurrencyRoundingPolicy):
            raise ValueError("rounding_policy must be CurrencyRoundingPolicy")
        _decimal(self.maximum_quote_age_seconds, field="maximum_quote_age_seconds")
        _decimal(self.minimum_guaranteed_profit, field="minimum_guaranteed_profit")
        _decimal(self.minimum_roi, field="minimum_roi")
        _decimal(self.commission_rate, field="commission_rate")
        _decimal(self.tax_rate, field="tax_rate")
        if self.commission_rate >= Decimal("1") or self.tax_rate >= Decimal("1"):
            raise ValueError("commission_rate and tax_rate must be below 1")
        if self.maximum_exposure is not None:
            _decimal(
                self.maximum_exposure,
                field="maximum_exposure",
                minimum=Decimal("0.0000000001"),
            )
        if self.maximum_margin_drift is not None:
            _decimal(self.maximum_margin_drift, field="maximum_margin_drift")


@dataclass(frozen=True, slots=True)
class OperationalAssumptions:
    """Assumptions attached to actionable output for auditability."""

    currency: str
    bankroll: Decimal
    maximum_exposure: Decimal
    minimum_guaranteed_profit: Decimal
    minimum_roi: Decimal
    maximum_quote_age_seconds: Decimal
    maximum_margin_drift: Decimal | None
    commission_rate: Decimal
    tax_rate: Decimal


@dataclass(frozen=True, slots=True)
class LifecycleEvaluation:
    """Result of revalidating one theoretical opportunity against current quotes."""

    state: LifecycleState
    reason: LifecycleReason
    theoretical_profit_margin: Decimal
    stake_plan: StakePlan | None
    gross_guaranteed_profit: Decimal | None
    net_guaranteed_profit: Decimal | None
    net_roi: Decimal | None
    assumptions: OperationalAssumptions
