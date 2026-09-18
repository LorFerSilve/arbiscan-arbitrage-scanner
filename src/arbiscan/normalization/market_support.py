"""Explicit runtime support policy for canonical market families."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from arbiscan.domain import (
    AsianHandicapLineClass,
    Market,
    MarketKind,
    MarketPeriod,
    Sport,
    asian_handicap_line_profile,
)


class MarketSupportStatus(StrEnum):
    """Whether a canonical market may enter generic arbitrage detection."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class MarketSupportDecision:
    """Deterministic explanation of one canonical market support decision."""

    status: MarketSupportStatus
    detail: str

    @property
    def supported(self) -> bool:
        return self.status is MarketSupportStatus.SUPPORTED


def is_push_free_football_total_line(line: Decimal) -> bool:
    """Return whether a football total line has exactly one half-goal boundary.

    Phase 17.2 supports positive x.5 lines only. Integer totals can settle PUSH,
    while quarter lines can settle HALF-WIN/HALF-LOSS; neither settlement class is
    represented by the current two-outcome theoretical-arbitrage model.
    """
    if type(line) is not Decimal or not line.is_finite() or line <= Decimal("0"):
        return False
    doubled = line * Decimal("2")
    if doubled != doubled.to_integral_value():
        return False
    return int(doubled) % 2 == 1


def is_push_free_football_handicap_line(line: Decimal) -> bool:
    """Return whether ordinary two-outcome math safely models this handicap line."""
    if type(line) is not Decimal or not line.is_finite():
        return False
    return asian_handicap_line_profile(line).line_class is AsianHandicapLineClass.HALF_GOAL


def assess_market_support(*, sport: Sport, market: Market) -> MarketSupportDecision:
    """Apply the currently enabled market-family boundary."""
    if not isinstance(sport, Sport):
        raise ValueError("sport must be Sport")
    if not isinstance(market, Market):
        raise ValueError("market must be Market")

    if market.kind in {
        MarketKind.MATCH_WINNER_2_WAY,
        MarketKind.MATCH_WINNER_3_WAY,
    }:
        return MarketSupportDecision(
            MarketSupportStatus.SUPPORTED,
            "winner market belongs to the validated baseline",
        )

    if market.kind is MarketKind.TOTAL_POINTS:
        if sport is not Sport.FOOTBALL:
            return MarketSupportDecision(
                MarketSupportStatus.UNSUPPORTED,
                "Phase 17.2 enables totals only for football",
            )
        if market.period is not MarketPeriod.REGULATION:
            return MarketSupportDecision(
                MarketSupportStatus.UNSUPPORTED,
                "Phase 17.2 football totals require regulation-time settlement",
            )
        if market.line is None or not is_push_free_football_total_line(market.line):
            return MarketSupportDecision(
                MarketSupportStatus.UNSUPPORTED,
                "Phase 17.2 football totals require a positive push-free half-goal line (x.5)",
            )
        return MarketSupportDecision(
            MarketSupportStatus.SUPPORTED,
            "football regulation total uses a push-free half-goal line",
        )

    if market.kind is MarketKind.HANDICAP:
        if sport is not Sport.FOOTBALL:
            return MarketSupportDecision(
                MarketSupportStatus.UNSUPPORTED,
                "Phase 17.3 enables handicaps only for football",
            )
        if market.period is not MarketPeriod.REGULATION:
            return MarketSupportDecision(
                MarketSupportStatus.UNSUPPORTED,
                "Phase 17.3 football handicaps require regulation-time settlement",
            )
        if market.line is None or not is_push_free_football_handicap_line(market.line):
            return MarketSupportDecision(
                MarketSupportStatus.UNSUPPORTED,
                (
                    "Phase 17.3 football handicaps require a half-goal line; "
                    "integer PUSH and quarter-line split settlements need the "
                    "settlement-aware payout path"
                ),
            )
        return MarketSupportDecision(
            MarketSupportStatus.SUPPORTED,
            "football regulation handicap uses a push-free half-goal line",
        )

    return MarketSupportDecision(
        MarketSupportStatus.UNSUPPORTED,
        f"market family {market.kind.value!r} is not enabled for generic arbitrage yet",
    )
