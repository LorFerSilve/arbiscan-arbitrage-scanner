"""Canonical Asian-handicap line geometry and settlement semantics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum

from arbiscan.domain.errors import DomainValidationError

_ZERO = Decimal("0")
_HALF = Decimal("0.5")
_ONE = Decimal("1")
_TWO = Decimal("2")
_FOUR = Decimal("4")


class AsianHandicapLineClass(StrEnum):
    """Settlement geometry of one signed participant-1 handicap line."""

    HALF_GOAL = "half_goal"
    INTEGER = "integer"
    QUARTER = "quarter"
    UNSUPPORTED = "unsupported"


class AsianHandicapSettlementResult(StrEnum):
    """Canonical result states needed to settle one Asian-handicap selection."""

    WIN = "win"
    HALF_WIN = "half_win"
    PUSH = "push"
    HALF_LOSS = "half_loss"
    LOSS = "loss"


@dataclass(frozen=True, slots=True)
class AsianHandicapComponent:
    """One ordinary handicap component and its fraction of the original stake."""

    line: Decimal
    stake_fraction: Decimal

    def __post_init__(self) -> None:
        if type(self.line) is not Decimal or not self.line.is_finite():
            raise DomainValidationError("Asian handicap component line must be finite Decimal")
        if type(self.stake_fraction) is not Decimal or not self.stake_fraction.is_finite():
            raise DomainValidationError(
                "Asian handicap component stake_fraction must be finite Decimal"
            )
        if self.stake_fraction <= _ZERO or self.stake_fraction > _ONE:
            raise DomainValidationError("Asian handicap component stake_fraction must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class AsianHandicapLineProfile:
    """Exact settlement decomposition for one signed Asian-handicap line."""

    line: Decimal
    line_class: AsianHandicapLineClass
    components: tuple[AsianHandicapComponent, ...]

    def __post_init__(self) -> None:
        if type(self.line) is not Decimal or not self.line.is_finite():
            raise DomainValidationError("Asian handicap line must be finite Decimal")
        if not isinstance(self.line_class, AsianHandicapLineClass):
            raise DomainValidationError("Asian handicap line_class is invalid")
        components = tuple(self.components)
        if any(not isinstance(value, AsianHandicapComponent) for value in components):
            raise DomainValidationError(
                "Asian handicap components must contain AsianHandicapComponent values"
            )
        if self.line_class is AsianHandicapLineClass.UNSUPPORTED:
            if components:
                raise DomainValidationError(
                    "unsupported Asian handicap line cannot have components"
                )
        else:
            total = sum((value.stake_fraction for value in components), _ZERO)
            if total != _ONE:
                raise DomainValidationError("Asian handicap component fractions must sum to one")
        object.__setattr__(self, "components", components)

    @property
    def generic_two_outcome_safe(self) -> bool:
        """Whether ordinary win/lose arbitrage and staking math is sufficient."""
        return self.line_class is AsianHandicapLineClass.HALF_GOAL


@dataclass(frozen=True, slots=True)
class AsianHandicapSettlement:
    """One settled selection with exact gross-return multiplier on original stake."""

    result: AsianHandicapSettlementResult
    gross_return_multiplier: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.result, AsianHandicapSettlementResult):
            raise DomainValidationError("Asian handicap settlement result is invalid")
        if (
            type(self.gross_return_multiplier) is not Decimal
            or not self.gross_return_multiplier.is_finite()
            or self.gross_return_multiplier < _ZERO
        ):
            raise DomainValidationError(
                "Asian handicap gross return multiplier must be finite non-negative Decimal"
            )


def asian_handicap_line_profile(line: Decimal) -> AsianHandicapLineProfile:
    """Classify a signed line and decompose quarter-lines into equal half-stakes."""
    if type(line) is not Decimal or not line.is_finite():
        raise DomainValidationError("Asian handicap line must be finite Decimal")

    quarter_units = line * _FOUR
    if quarter_units != quarter_units.to_integral_value():
        return AsianHandicapLineProfile(
            line=line,
            line_class=AsianHandicapLineClass.UNSUPPORTED,
            components=(),
        )

    units = int(quarter_units)
    remainder = units % 4
    if remainder == 0:
        return AsianHandicapLineProfile(
            line=line,
            line_class=AsianHandicapLineClass.INTEGER,
            components=(AsianHandicapComponent(line=line, stake_fraction=_ONE),),
        )
    if remainder == 2:
        return AsianHandicapLineProfile(
            line=line,
            line_class=AsianHandicapLineClass.HALF_GOAL,
            components=(AsianHandicapComponent(line=line, stake_fraction=_ONE),),
        )

    doubled = line * _TWO
    lower = doubled.to_integral_value(rounding=ROUND_FLOOR) / _TWO
    upper = doubled.to_integral_value(rounding=ROUND_CEILING) / _TWO
    if lower == upper:
        raise DomainValidationError("quarter-line decomposition failed")
    return AsianHandicapLineProfile(
        line=line,
        line_class=AsianHandicapLineClass.QUARTER,
        components=(
            AsianHandicapComponent(line=lower, stake_fraction=_HALF),
            AsianHandicapComponent(line=upper, stake_fraction=_HALF),
        ),
    )


def settle_asian_handicap(
    *,
    line: Decimal,
    goal_difference: int,
    decimal_odds: Decimal,
) -> AsianHandicapSettlement:
    """Settle one selection from that participant's regulation-time goal difference.

    ``goal_difference`` is goals scored by the selected participant minus goals
    scored by its opponent. Quarter-lines are evaluated as two equal half-stakes.
    """
    if type(goal_difference) is not int:
        raise DomainValidationError("Asian handicap goal_difference must be int")
    if type(decimal_odds) is not Decimal or not decimal_odds.is_finite():
        raise DomainValidationError("Asian handicap decimal_odds must be finite Decimal")
    if decimal_odds <= _ONE:
        raise DomainValidationError("Asian handicap decimal_odds must be greater than one")

    profile = asian_handicap_line_profile(line)
    if profile.line_class is AsianHandicapLineClass.UNSUPPORTED:
        raise DomainValidationError("unsupported Asian handicap line granularity")

    component_results: list[AsianHandicapSettlementResult] = []
    gross = _ZERO
    for component in profile.components:
        adjusted = Decimal(goal_difference) + component.line
        if adjusted > _ZERO:
            component_result = AsianHandicapSettlementResult.WIN
            component_return = decimal_odds
        elif adjusted == _ZERO:
            component_result = AsianHandicapSettlementResult.PUSH
            component_return = _ONE
        else:
            component_result = AsianHandicapSettlementResult.LOSS
            component_return = _ZERO
        component_results.append(component_result)
        gross += component.stake_fraction * component_return

    states = set(component_results)
    if states == {AsianHandicapSettlementResult.WIN}:
        result = AsianHandicapSettlementResult.WIN
    elif states == {AsianHandicapSettlementResult.LOSS}:
        result = AsianHandicapSettlementResult.LOSS
    elif states == {AsianHandicapSettlementResult.PUSH}:
        result = AsianHandicapSettlementResult.PUSH
    elif states == {AsianHandicapSettlementResult.WIN, AsianHandicapSettlementResult.PUSH}:
        result = AsianHandicapSettlementResult.HALF_WIN
    elif states == {AsianHandicapSettlementResult.LOSS, AsianHandicapSettlementResult.PUSH}:
        result = AsianHandicapSettlementResult.HALF_LOSS
    else:
        raise DomainValidationError("unexpected Asian handicap component settlement combination")

    return AsianHandicapSettlement(result=result, gross_return_multiplier=gross)
