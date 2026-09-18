"""Phase 17.2 market-family support policy tests."""

from decimal import Decimal

from arbiscan.domain import EventId, Market, MarketId, MarketKind, MarketPeriod, Sport
from arbiscan.normalization import (
    MarketSupportPurpose,
    MarketSupportStatus,
    assess_market_support,
    is_push_free_football_handicap_line,
    is_push_free_football_total_line,
)


def _market(
    *,
    kind: MarketKind,
    period: MarketPeriod = MarketPeriod.REGULATION,
    line: Decimal | None = None,
) -> Market:
    return Market(
        id=MarketId(f"market:{kind.value}:{period.value}:{line}"),
        event_id=EventId("event:test"),
        kind=kind,
        period=period,
        line=line,
    )


def test_push_free_football_total_line_accepts_only_positive_half_goal_lines() -> None:
    assert is_push_free_football_total_line(Decimal("0.5"))
    assert is_push_free_football_total_line(Decimal("2.5"))
    assert is_push_free_football_total_line(Decimal("10.5"))

    for line in (
        Decimal("0"),
        Decimal("-0.5"),
        Decimal("2"),
        Decimal("2.25"),
        Decimal("2.75"),
        Decimal("NaN"),
    ):
        assert not is_push_free_football_total_line(line)


def test_phase17_2_supports_regulation_football_half_goal_totals() -> None:
    decision = assess_market_support(
        sport=Sport.FOOTBALL,
        market=_market(kind=MarketKind.TOTAL_POINTS, line=Decimal("2.5")),
    )

    assert decision.status is MarketSupportStatus.SUPPORTED
    assert decision.supported


def test_phase17_2_rejects_push_and_split_settlement_total_lines() -> None:
    for line in (Decimal("2"), Decimal("2.25"), Decimal("2.75")):
        decision = assess_market_support(
            sport=Sport.FOOTBALL,
            market=_market(kind=MarketKind.TOTAL_POINTS, line=line),
        )
        assert decision.status is MarketSupportStatus.UNSUPPORTED
        assert not decision.supported


def test_phase17_2_rejects_non_regulation_or_non_football_totals() -> None:
    full_event = assess_market_support(
        sport=Sport.FOOTBALL,
        market=_market(
            kind=MarketKind.TOTAL_POINTS,
            period=MarketPeriod.FULL_EVENT,
            line=Decimal("2.5"),
        ),
    )
    tennis = assess_market_support(
        sport=Sport.TENNIS,
        market=_market(kind=MarketKind.TOTAL_POINTS, line=Decimal("2.5")),
    )

    assert full_event.status is MarketSupportStatus.UNSUPPORTED
    assert tennis.status is MarketSupportStatus.UNSUPPORTED


def test_phase17_3_supports_only_push_free_regulation_football_handicaps() -> None:
    for line in (Decimal("-2.5"), Decimal("-0.5"), Decimal("0.5"), Decimal("3.5")):
        assert is_push_free_football_handicap_line(line)
        decision = assess_market_support(
            sport=Sport.FOOTBALL,
            market=_market(kind=MarketKind.HANDICAP, line=line),
        )
        assert decision.status is MarketSupportStatus.SUPPORTED

    for line in (
        Decimal("-1"),
        Decimal("0"),
        Decimal("1"),
        Decimal("-0.25"),
        Decimal("0.25"),
        Decimal("0.75"),
        Decimal("0.3"),
    ):
        assert not is_push_free_football_handicap_line(line)
        decision = assess_market_support(
            sport=Sport.FOOTBALL,
            market=_market(kind=MarketKind.HANDICAP, line=line),
        )
        assert decision.status is MarketSupportStatus.UNSUPPORTED


def test_phase17_3_rejects_non_regulation_or_non_football_handicaps() -> None:
    first_half = assess_market_support(
        sport=Sport.FOOTBALL,
        market=_market(
            kind=MarketKind.HANDICAP,
            period=MarketPeriod.FIRST_HALF,
            line=Decimal("-0.5"),
        ),
    )
    tennis = assess_market_support(
        sport=Sport.TENNIS,
        market=_market(kind=MarketKind.HANDICAP, line=Decimal("-0.5")),
    )

    assert first_half.status is MarketSupportStatus.UNSUPPORTED
    assert tennis.status is MarketSupportStatus.UNSUPPORTED


def test_baseline_winner_markets_remain_supported() -> None:
    winner = assess_market_support(
        sport=Sport.FOOTBALL,
        market=_market(kind=MarketKind.MATCH_WINNER_3_WAY, line=None),
    )

    assert winner.status is MarketSupportStatus.SUPPORTED


def test_phase17_4_supports_only_regulation_football_btts() -> None:
    supported = assess_market_support(
        sport=Sport.FOOTBALL,
        market=_market(
            kind=MarketKind.BOTH_TEAMS_TO_SCORE,
            period=MarketPeriod.REGULATION,
            line=None,
        ),
    )
    first_half = assess_market_support(
        sport=Sport.FOOTBALL,
        market=_market(
            kind=MarketKind.BOTH_TEAMS_TO_SCORE,
            period=MarketPeriod.FIRST_HALF,
            line=None,
        ),
    )
    tennis = assess_market_support(
        sport=Sport.TENNIS,
        market=_market(
            kind=MarketKind.BOTH_TEAMS_TO_SCORE,
            period=MarketPeriod.REGULATION,
            line=None,
        ),
    )

    assert supported.status is MarketSupportStatus.SUPPORTED
    assert supported.supported
    assert first_half.status is MarketSupportStatus.UNSUPPORTED
    assert tennis.status is MarketSupportStatus.UNSUPPORTED


def test_phase17_5_draw_no_bet_requires_explicit_settlement_aware_path() -> None:
    market = _market(kind=MarketKind.HANDICAP, line=Decimal("0"))

    generic = assess_market_support(
        sport=Sport.FOOTBALL,
        market=market,
    )
    settlement_aware = assess_market_support(
        sport=Sport.FOOTBALL,
        market=market,
        purpose=MarketSupportPurpose.SETTLEMENT_AWARE,
    )

    assert generic.status is MarketSupportStatus.UNSUPPORTED
    assert settlement_aware.status is MarketSupportStatus.SUPPORTED
    assert settlement_aware.supported


def test_phase17_5_settlement_aware_path_does_not_unlock_other_integer_handicaps() -> None:
    for line in (Decimal("-2"), Decimal("-1"), Decimal("1"), Decimal("2")):
        decision = assess_market_support(
            sport=Sport.FOOTBALL,
            market=_market(kind=MarketKind.HANDICAP, line=line),
            purpose=MarketSupportPurpose.SETTLEMENT_AWARE,
        )
        assert decision.status is MarketSupportStatus.UNSUPPORTED
