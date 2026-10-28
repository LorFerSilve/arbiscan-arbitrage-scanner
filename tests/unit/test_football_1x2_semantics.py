"""Offline source-contract tests for football home/away and regulation 1X2."""

from decimal import Decimal

import pytest

from arbiscan.domain import MarketKind, MarketPeriod, ParticipantId, Sport
from arbiscan.normalization.football_1x2 import (
    FOOTBALL_REGULATION_1X2,
    FixtureSideAlignment,
    Football1X2Side,
    assess_oddspapi_fixture_order,
    consistent_oddspapi_regulation_1x2_settlement,
    football_regulation_1x2_winner,
    is_documented_oddspapi_football_1x2,
    oddspapi_1x2_side,
    the_odds_api_soccer_h2h_sides,
)
from arbiscan.providers.oddspapi import _is_supported_market, _market_records


def _market(
    *,
    market_id: int = 101,
    name: str = "Full Time Result",
    period: str = "fulltime",
    market_type: str = "1x2",
    handicap: int = 0,
    player_prop: bool = False,
    outcome_names: tuple[str, str, str] = ("1", "X", "2"),
) -> dict[str, object]:
    return {
        "marketId": market_id,
        "marketLength": 3,
        "marketName": name,
        "playerProp": player_prop,
        "sportId": 10,
        "handicap": handicap,
        "period": period,
        "marketType": market_type,
        "outcomes": [
            {"outcomeId": 101 + index, "outcomeName": outcome}
            for index, outcome in enumerate(outcome_names)
        ],
    }


def _is_parsed_market_supported(market: dict[str, object]) -> bool:
    records = _market_records([market])
    return any(_is_supported_market(record, Sport.FOOTBALL) for record in records.values())


def test_only_documented_odds_papi_sport10_market101_is_supported() -> None:
    assert _is_parsed_market_supported(_market())
    for kwargs in (
        {"market_id": 901},
        {"period": "result"},
        {"period": "fulltime+overtime"},
        {"name": "To Qualify"},
        {"market_type": "winner"},
        {"handicap": 1},
        {"player_prop": True},
        {"outcome_names": ("2", "X", "1")},
        {"outcome_names": ("1", "X", "3")},
    ):
        assert not _is_parsed_market_supported(_market(**kwargs))  # type: ignore[arg-type]


def test_1x2_contract_has_explicit_regulation_semantics_and_outcome_ids() -> None:
    assert FOOTBALL_REGULATION_1X2.kind is MarketKind.MATCH_WINNER_3_WAY
    assert FOOTBALL_REGULATION_1X2.period is MarketPeriod.REGULATION
    assert is_documented_oddspapi_football_1x2(
        market_id="101",
        sport_id=10,
        market_name="Full Time Result",
        period="fulltime",
        market_type="1x2",
        handicap=Decimal(0),
        player_prop=False,
        outcomes={"101": "1", "102": "X", "103": "2"},
    )
    assert oddspapi_1x2_side("101") is Football1X2Side.HOME
    assert oddspapi_1x2_side("102") is Football1X2Side.DRAW
    assert oddspapi_1x2_side("103") is Football1X2Side.AWAY
    assert oddspapi_1x2_side("999") is None


def test_soccer_h2h_labels_require_exact_home_draw_away_set() -> None:
    assert the_odds_api_soccer_h2h_sides(
        home_name="Chelsea",
        away_name="Arsenal",
        outcome_labels=("Arsenal", "Draw", "Chelsea"),
    ) == (
        Football1X2Side.AWAY,
        Football1X2Side.DRAW,
        Football1X2Side.HOME,
    )
    assert (
        the_odds_api_soccer_h2h_sides(
            home_name="Chelsea",
            away_name="Arsenal",
            outcome_labels=("Chelsea", "Arsenal"),
        )
        is None
    )
    assert (
        the_odds_api_soccer_h2h_sides(
            home_name="Chelsea",
            away_name="Arsenal",
            outcome_labels=("Chelsea", "Chelsea", "Draw"),
        )
        is None
    )
    assert (
        the_odds_api_soccer_h2h_sides(
            home_name="Chelsea",
            away_name="Arsenal",
            outcome_labels=("Chelsea Women", "Draw", "Arsenal"),
        )
        is None
    )


def test_fixture_order_is_relative_to_reference_not_auto_certification() -> None:
    chelsea = ParticipantId("participant:chelsea")
    arsenal = ParticipantId("participant:arsenal")
    others = ParticipantId("participant:others")
    assert (
        assess_oddspapi_fixture_order(
            reference_home=chelsea,
            reference_away=arsenal,
            participant1=chelsea,
            participant2=arsenal,
        )
        is FixtureSideAlignment.ALIGNED
    )
    assert (
        assess_oddspapi_fixture_order(
            reference_home=chelsea,
            reference_away=arsenal,
            participant1=arsenal,
            participant2=chelsea,
        )
        is FixtureSideAlignment.REVERSED
    )
    assert (
        assess_oddspapi_fixture_order(
            reference_home=chelsea,
            reference_away=arsenal,
            participant1=chelsea,
            participant2=others,
        )
        is FixtureSideAlignment.CONFLICT
    )


@pytest.mark.parametrize(
    ("home", "away", "winner"),
    [
        (2, 1, Football1X2Side.HOME),
        (0, 0, Football1X2Side.DRAW),
        (1, 1, Football1X2Side.DRAW),
        (0, 2, Football1X2Side.AWAY),
    ],
)
def test_regulation_score_uses_only_90_minute_goals(
    home: int, away: int, winner: Football1X2Side
) -> None:
    assert football_regulation_1x2_winner(home_goals=home, away_goals=away) is winner


@pytest.mark.parametrize(("home", "away"), [(True, 1), (-1, 0), (1.5, 1), (1, "0")])
def test_invalid_regulation_scores_fail_closed(home: object, away: object) -> None:
    with pytest.raises(ValueError, match="regulation scores"):
        football_regulation_1x2_winner(
            home_goals=home,
            away_goals=away,  # type: ignore[arg-type]
        )


def test_complete_oddspapi_1x2_grade_must_match_regulation_result() -> None:
    home_win = {"101": "WIN", "102": "LOSE", "103": "LOSE"}
    draw = {"101": "LOSE", "102": "WIN", "103": "LOSE"}
    away_win = {"101": "LOSE", "102": "LOSE", "103": "WIN"}
    assert consistent_oddspapi_regulation_1x2_settlement(
        grades=home_win, verified_home_goals=2, verified_away_goals=1
    )
    assert consistent_oddspapi_regulation_1x2_settlement(
        grades=draw, verified_home_goals=1, verified_away_goals=1
    )
    assert consistent_oddspapi_regulation_1x2_settlement(
        grades=away_win, verified_home_goals=0, verified_away_goals=2
    )
    # Even if a cup tie ends 2-1 after extra time, regulation 1-1 stays a draw.
    assert consistent_oddspapi_regulation_1x2_settlement(
        grades=draw, verified_home_goals=1, verified_away_goals=1
    )
    assert not consistent_oddspapi_regulation_1x2_settlement(
        grades=home_win, verified_home_goals=1, verified_away_goals=1
    )


@pytest.mark.parametrize(
    "grades",
    [
        {"101": "WIN", "102": "LOSE"},
        {"101": "WIN", "102": "LOSE", "103": "PUSH"},
        {"101": "WIN", "102": "LOSE", "103": "UNDECIDED"},
        {"101": "WIN", "102": "LOSE", "103": "CANCELLED"},
        {"101": "WIN", "102": "LOSE", "103": "HALFLOSS"},
        {"101": "WIN", "102": "WIN", "103": "LOSE"},
        {"101": "WIN", "102": "LOSE", "103": "LOSE", "104": "LOSE"},
    ],
)
def test_nonstandard_1x2_settlement_does_not_pass(grades: dict[str, str]) -> None:
    assert not consistent_oddspapi_regulation_1x2_settlement(
        grades=grades, verified_home_goals=2, verified_away_goals=1
    )
