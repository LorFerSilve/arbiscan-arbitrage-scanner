"""Phase 17.3 canonical Asian-handicap settlement semantics."""

from decimal import Decimal

from arbiscan.domain import (
    AsianHandicapLineClass,
    AsianHandicapSettlementResult,
    asian_handicap_line_profile,
    settle_asian_handicap,
)


def test_line_profile_classifies_half_integer_quarter_and_unsupported_lines() -> None:
    half = asian_handicap_line_profile(Decimal("-0.5"))
    integer = asian_handicap_line_profile(Decimal("-1"))
    quarter_negative = asian_handicap_line_profile(Decimal("-0.25"))
    quarter_positive = asian_handicap_line_profile(Decimal("0.25"))
    unsupported = asian_handicap_line_profile(Decimal("0.3"))

    assert half.line_class is AsianHandicapLineClass.HALF_GOAL
    assert tuple((item.line, item.stake_fraction) for item in half.components) == (
        (Decimal("-0.5"), Decimal("1")),
    )

    assert integer.line_class is AsianHandicapLineClass.INTEGER
    assert tuple((item.line, item.stake_fraction) for item in integer.components) == (
        (Decimal("-1"), Decimal("1")),
    )

    assert quarter_negative.line_class is AsianHandicapLineClass.QUARTER
    assert tuple(
        (item.line, item.stake_fraction) for item in quarter_negative.components
    ) == (
        (Decimal("-0.5"), Decimal("0.5")),
        (Decimal("0"), Decimal("0.5")),
    )

    assert quarter_positive.line_class is AsianHandicapLineClass.QUARTER
    assert tuple(
        (item.line, item.stake_fraction) for item in quarter_positive.components
    ) == (
        (Decimal("0"), Decimal("0.5")),
        (Decimal("0.5"), Decimal("0.5")),
    )

    assert unsupported.line_class is AsianHandicapLineClass.UNSUPPORTED
    assert unsupported.components == ()


def test_half_goal_handicap_has_only_win_or_loss_settlement() -> None:
    win = settle_asian_handicap(
        line=Decimal("-0.5"),
        goal_difference=1,
        decimal_odds=Decimal("2.10"),
    )
    loss = settle_asian_handicap(
        line=Decimal("-0.5"),
        goal_difference=0,
        decimal_odds=Decimal("2.10"),
    )

    assert win.result is AsianHandicapSettlementResult.WIN
    assert win.gross_return_multiplier == Decimal("2.10")
    assert loss.result is AsianHandicapSettlementResult.LOSS
    assert loss.gross_return_multiplier == Decimal("0")


def test_integer_handicap_models_push_as_stake_return() -> None:
    settlement = settle_asian_handicap(
        line=Decimal("-1"),
        goal_difference=1,
        decimal_odds=Decimal("2.20"),
    )

    assert settlement.result is AsianHandicapSettlementResult.PUSH
    assert settlement.gross_return_multiplier == Decimal("1")


def test_quarter_handicap_models_half_win_and_half_loss_payouts() -> None:
    half_win = settle_asian_handicap(
        line=Decimal("0.25"),
        goal_difference=0,
        decimal_odds=Decimal("2.20"),
    )
    half_loss = settle_asian_handicap(
        line=Decimal("-0.25"),
        goal_difference=0,
        decimal_odds=Decimal("2.20"),
    )

    assert half_win.result is AsianHandicapSettlementResult.HALF_WIN
    assert half_win.gross_return_multiplier == Decimal("1.60")
    assert half_loss.result is AsianHandicapSettlementResult.HALF_LOSS
    assert half_loss.gross_return_multiplier == Decimal("0.5")


def test_three_quarter_line_splits_across_neighboring_half_goal_boundaries() -> None:
    profile = asian_handicap_line_profile(Decimal("-0.75"))
    settlement = settle_asian_handicap(
        line=Decimal("-0.75"),
        goal_difference=1,
        decimal_odds=Decimal("1.90"),
    )

    assert tuple((item.line, item.stake_fraction) for item in profile.components) == (
        (Decimal("-1"), Decimal("0.5")),
        (Decimal("-0.5"), Decimal("0.5")),
    )
    assert settlement.result is AsianHandicapSettlementResult.HALF_WIN
    assert settlement.gross_return_multiplier == Decimal("1.45")


def test_only_half_goal_profile_is_safe_for_generic_two_outcome_math() -> None:
    assert asian_handicap_line_profile(Decimal("-0.5")).generic_two_outcome_safe
    assert not asian_handicap_line_profile(Decimal("0")).generic_two_outcome_safe
    assert not asian_handicap_line_profile(Decimal("0.25")).generic_two_outcome_safe
    assert not asian_handicap_line_profile(Decimal("0.3")).generic_two_outcome_safe
