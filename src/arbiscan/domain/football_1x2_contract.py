"""Exact Oddspapi soccer 1X2 schema contract shared without provider imports.

Kept in the dependency-minimal domain package so the provider adapter can
validate source market 101 without importing the normalization package.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

ODDSPAPI_1X2_LABELS: Mapping[str, str] = {"101": "1", "102": "X", "103": "2"}


def is_documented_oddspapi_football_1x2(
    *,
    market_id: str,
    sport_id: int,
    market_name: str,
    period: str,
    market_type: str,
    handicap: Decimal,
    player_prop: bool,
    outcomes: Mapping[str, str],
) -> bool:
    """Only documented soccer market 101/101-103, with regulation semantics."""
    return (
        market_id == "101"
        and sport_id == 10
        and market_name.casefold() == "full time result"
        and period == "fulltime"
        and market_type == "1x2"
        and handicap == Decimal(0)
        and not player_prop
        and dict(outcomes) == dict(ODDSPAPI_1X2_LABELS)
    )
