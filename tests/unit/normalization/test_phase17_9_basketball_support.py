"""Phase 17.9 basketball market-support and settlement-boundary tests."""

from decimal import Decimal

from arbiscan.domain import EventId, Market, MarketId, MarketKind, MarketPeriod, Sport
from arbiscan.normalization import (
    MarketSupportStatus,
    assess_market_support,
    is_push_free_basketball_handicap_line,
    is_push_free_basketball_total_line,
)


def _market(*, kind: MarketKind, period: MarketPeriod, line: Decimal) -> Market:
    return Market(
        id=MarketId(f"market:phase17-9:{kind.value}:{period.value}:{line}"),
        event_id=EventId("event:phase17-9:test"),
        kind=kind,
        period=period,
        line=line,
    )


def test_basketball_push_free_helpers_accept_only_half_point_geometry() -> None:
    for line in (Decimal("0.5"), Decimal("3.5"), Decimal("215.5")):
        assert is_push_free_basketball_total_line(line)

    for line in (Decimal("-9.5"), Decimal("-3.5"), Decimal("3.5")):
        assert is_push_free_basketball_handicap_line(line)

    for line in (Decimal("0"), Decimal("3"), Decimal("3.25"), Decimal("3.75")):
        assert not is_push_free_basketball_handicap_line(line)

    for line in (
        Decimal("0"),
        Decimal("-0.5"),
        Decimal("215"),
        Decimal("215.25"),
        Decimal("215.75"),
    ):
        assert not is_push_free_basketball_total_line(line)


def test_phase17_9_supports_full_event_half_point_basketball_totals_and_spreads() -> None:
    total = assess_market_support(
        sport=Sport.BASKETBALL,
        market=_market(
            kind=MarketKind.TOTAL_POINTS,
            period=MarketPeriod.FULL_EVENT,
            line=Decimal("215.5"),
        ),
    )
    spread = assess_market_support(
        sport=Sport.BASKETBALL,
        market=_market(
            kind=MarketKind.HANDICAP,
            period=MarketPeriod.FULL_EVENT,
            line=Decimal("-3.5"),
        ),
    )

    assert total.status is MarketSupportStatus.SUPPORTED
    assert spread.status is MarketSupportStatus.SUPPORTED


def test_phase17_9_rejects_regulation_period_and_push_or_split_lines() -> None:
    for kind, line in (
        (MarketKind.TOTAL_POINTS, Decimal("215.5")),
        (MarketKind.HANDICAP, Decimal("-3.5")),
    ):
        decision = assess_market_support(
            sport=Sport.BASKETBALL,
            market=_market(kind=kind, period=MarketPeriod.REGULATION, line=line),
        )
        assert decision.status is MarketSupportStatus.UNSUPPORTED

    for kind, lines in (
        (
            MarketKind.TOTAL_POINTS,
            (Decimal("215"), Decimal("215.25"), Decimal("215.75")),
        ),
        (
            MarketKind.HANDICAP,
            (Decimal("-3"), Decimal("-3.25"), Decimal("-3.75"), Decimal("0")),
        ),
    ):
        for line in lines:
            decision = assess_market_support(
                sport=Sport.BASKETBALL,
                market=_market(kind=kind, period=MarketPeriod.FULL_EVENT, line=line),
            )
            assert decision.status is MarketSupportStatus.UNSUPPORTED
