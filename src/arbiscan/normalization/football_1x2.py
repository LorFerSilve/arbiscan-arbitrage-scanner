"""Source-backed football 1X2 semantics; no unverified quote authorization.

OddsPapi V4 market 101 is Full Time Result for soccer (sport 10), with
outcomes 101=1 (home), 102=X (draw), 103=2 (away). The 'fulltime' period
is regulation time. The fixture fields participant1/participant2, however,
do not independently prove home/away ordering for every fixture.

Do not use this module to approve a bookmaker's void/abandonment rules or to
manufacture a Phase-8 event match. It is strictly a semantic verifier.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from arbiscan.domain import MarketKind, MarketPeriod, ParticipantId
from arbiscan.normalization.markets import MarketSemantic


class Football1X2Side(StrEnum):
    HOME = "home"
    DRAW = "draw"
    AWAY = "away"


class FixtureSideAlignment(StrEnum):
    """Source participant ordering relative to a reviewed home/away reference."""

    ALIGNED = "aligned"
    REVERSED = "reversed"
    CONFLICT = "conflict"


def assess_oddspapi_fixture_order(
    *,
    reference_home: ParticipantId,
    reference_away: ParticipantId,
    participant1: ParticipantId,
    participant2: ParticipantId,
) -> FixtureSideAlignment:
    """Compare team *identities*; cannot independently certify provider roles.

    The reference must have explicit home/away roles. Agreement with another
    source is evidence, not provider documentation or bookmaker-settlement proof.
    """
    if reference_home == reference_away or participant1 == participant2:
        return FixtureSideAlignment.CONFLICT
    if (participant1, participant2) == (reference_home, reference_away):
        return FixtureSideAlignment.ALIGNED
    if (participant1, participant2) == (reference_away, reference_home):
        return FixtureSideAlignment.REVERSED
    return FixtureSideAlignment.CONFLICT


# Vendor IDs are contract-specific. No guessing based on outcome array order.
ODDSPAPI_1X2_SIDES: Mapping[str, Football1X2Side] = {
    "101": Football1X2Side.HOME,
    "102": Football1X2Side.DRAW,
    "103": Football1X2Side.AWAY,
}
FOOTBALL_REGULATION_1X2 = MarketSemantic(
    kind=MarketKind.MATCH_WINNER_3_WAY,
    period=MarketPeriod.REGULATION,
)


def oddspapi_1x2_side(outcome_id: str) -> Football1X2Side | None:
    """Interpret an OddsPapi 1X2 outcome ID, not participant1/2 order."""
    return ODDSPAPI_1X2_SIDES.get(outcome_id)


def the_odds_api_soccer_h2h_sides(
    *,
    home_name: str,
    away_name: str,
    outcome_labels: tuple[str, ...],
) -> tuple[Football1X2Side, ...] | None:
    """Recognize the exact home/draw/away names of a three-way soccer h2h.

    The Odds API labels the teams explicitly in its source event. Do not
    normalize aliases or guess a role from the position of a label.
    """
    home, away = home_name.strip().casefold(), away_name.strip().casefold()
    if not home or not away or home == away or len(outcome_labels) != 3:
        return None
    by_label = {
        home: Football1X2Side.HOME,
        "draw": Football1X2Side.DRAW,
        away: Football1X2Side.AWAY,
    }
    if len(by_label) != 3:
        return None
    labels = tuple(label.strip().casefold() for label in outcome_labels)
    if set(labels) != set(by_label) or len(set(labels)) != 3:
        return None
    return tuple(by_label[label] for label in labels)


def football_regulation_1x2_winner(
    *,
    home_goals: int,
    away_goals: int,
) -> Football1X2Side:
    """Determine the winner from a verified *regulation-time* score only."""
    if (
        type(home_goals) is not int
        or type(away_goals) is not int
        or home_goals < 0
        or away_goals < 0
    ):
        raise ValueError("regulation scores must be non-negative integer goals")
    if home_goals > away_goals:
        return Football1X2Side.HOME
    if away_goals > home_goals:
        return Football1X2Side.AWAY
    return Football1X2Side.DRAW


def consistent_oddspapi_regulation_1x2_settlement(
    *,
    grades: Mapping[str, str],
    verified_home_goals: int,
    verified_away_goals: int,
) -> bool:
    """Validate complete WIN/LOSE grades against an independent 90-min score.

    Feed this only explicitly verified *home/away regulation* scores.
    OddsPapi scores.periods.fulltime expresses participant1/2 scores and
    cannot be passed as home/away unless that orientation has been proven.
    CANCELLED, PUSH, HALF*, UNDECIDED or missing outcomes fail closed. This
    does not prove a bookmaker's postponement/abandonment settlement policy.
    """
    if set(grades) != set(ODDSPAPI_1X2_SIDES):
        return False
    expected = football_regulation_1x2_winner(
        home_goals=verified_home_goals,
        away_goals=verified_away_goals,
    )
    return all(
        grades[key] == ("WIN" if side is expected else "LOSE")
        for key, side in ODDSPAPI_1X2_SIDES.items()
    )
