"""Phase 17.12 exchange back/lay liability, commission, and liquidity regressions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.arbitrage import (
    ArbitrageMathError,
    BookmakerBackStake,
    ExchangePriceObservation,
    ExchangeSide,
    ExchangeStake,
    assess_exchange_price_support,
    evaluate_exchange_portfolio,
    lay_liability,
)
from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    Provider,
    ProviderId,
    ProviderKind,
    QuoteId,
    QuoteStatus,
    SelectionId,
)

EVENT_ID = EventId("event:phase17-12:binary")
MARKET_ID = MarketId("market:phase17-12:binary")
A = SelectionId("selection:phase17-12:a")
B = SelectionId("selection:phase17-12:b")
NOW = datetime(2026, 9, 18, 15, 0, tzinfo=UTC)
EXCHANGE = Provider(
    id=ProviderId("exchange:phase17-12:betfair"),
    name="Fixture Exchange",
    kind=ProviderKind.EXCHANGE,
)
BOOKMAKER = Provider(
    id=ProviderId("bookmaker:phase17-12:fixture"),
    name="Fixture Bookmaker",
    kind=ProviderKind.BOOKMAKER,
)
TRANSPORT = ProviderId("provider:phase17-12:exchange-feed")


def _exchange_price(
    *,
    selection_id: SelectionId,
    side: ExchangeSide | None,
    odds: str = "2.8",
    available: str | None = "500",
    commission: str | None = "0.02",
    scope: str | None = "fixture-account:market",
    verified: bool = True,
    status: QuoteStatus = QuoteStatus.ACTIVE,
) -> ExchangePriceObservation:
    return ExchangePriceObservation(
        exchange_provider=EXCHANGE,
        transport_provider_id=TRANSPORT,
        event_id=EVENT_ID,
        market_id=MARKET_ID,
        selection_id=selection_id,
        decimal_price=Decimal(odds),
        status=status,
        side=side,
        available_stake=None if available is None else Decimal(available),
        commission_rate=None if commission is None else Decimal(commission),
        commission_scope=scope,
        settlement_rules_verified=verified,
    )


def _bookmaker_quote(*, selection_id: SelectionId, odds: str = "3.2") -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:phase17-12:{selection_id.value.rsplit(':', 1)[-1]}"),
        provider_id=BOOKMAKER.id,
        event_id=EVENT_ID,
        market_id=MARKET_ID,
        selection_id=selection_id,
        decimal_price=Decimal(odds),
        source_event_id="source:event",
        source_market_id="source:market",
        source_selection_id=selection_id.value,
        ingested_at=NOW,
        status=QuoteStatus.ACTIVE,
        trace_id="trace:phase17-12:bookmaker",
    )


def _expect_math_error(action: Callable[[], object], *, contains: str) -> None:
    try:
        action()
    except ArbitrageMathError as error:
        assert contains in str(error)
    else:
        raise AssertionError("expected ArbitrageMathError")


def test_lay_liability_is_stake_times_odds_minus_one() -> None:
    assert lay_liability(Decimal("10"), Decimal("13.5")) == Decimal("125")
    assert lay_liability(Decimal("100"), Decimal("1.9")) == Decimal("90")


def test_exchange_price_support_fails_closed_for_missing_execution_semantics() -> None:
    complete = _exchange_price(selection_id=A, side=ExchangeSide.LAY)
    assert assess_exchange_price_support(complete).eligible

    cases = (
        (replace(complete, side=None), "BACK/LAY side identity is missing"),
        (replace(complete, available_stake=None), "matched liquidity is missing"),
        (replace(complete, commission_rate=None), "commission rate is missing"),
        (
            replace(complete, commission_scope=None),
            "commission scope/account-market provenance is missing",
        ),
        (
            replace(complete, settlement_rules_verified=False),
            "settlement-rule equivalence is not verified",
        ),
        (replace(complete, status=QuoteStatus.SUSPENDED), "price is not active"),
    )

    for price, blocker in cases:
        decision = assess_exchange_price_support(price)
        assert not decision.eligible
        assert blocker in decision.blockers


def test_exchange_origin_must_be_explicit_provider_kind_exchange() -> None:
    bookmaker = Provider(
        id=ProviderId("bookmaker:phase17-12:not-an-exchange"),
        name="Not Exchange",
        kind=ProviderKind.BOOKMAKER,
    )

    _expect_math_error(
        lambda: ExchangePriceObservation(
            exchange_provider=bookmaker,
            transport_provider_id=TRANSPORT,
            event_id=EVENT_ID,
            market_id=MARKET_ID,
            selection_id=A,
            decimal_price=Decimal("2"),
            side=ExchangeSide.BACK,
        ),
        contains="ProviderKind.EXCHANGE",
    )


def test_exchange_stake_cannot_exceed_visible_matched_liquidity() -> None:
    price = _exchange_price(
        selection_id=A,
        side=ExchangeSide.LAY,
        available="50",
    )

    _expect_math_error(
        lambda: ExchangeStake(price=price, stake=Decimal("50.01")),
        contains="available matched liquidity",
    )


def test_bookmaker_back_plus_exchange_lay_is_commission_aware_arbitrage() -> None:
    bookmaker = BookmakerBackStake(
        quote=_bookmaker_quote(selection_id=A, odds="3.2"),
        price_provider=BOOKMAKER,
        stake=Decimal("100"),
    )
    lay = ExchangeStake(
        price=_exchange_price(
            selection_id=A,
            side=ExchangeSide.LAY,
            odds="2.8",
            available="200",
            commission="0.02",
        ),
        stake=Decimal("110"),
    )

    evaluation = evaluate_exchange_portfolio(
        bookmaker_backs=(bookmaker,),
        exchange_stakes=(lay,),
        expected_selection_ids=(A, B),
    )

    by_winner = {scenario.winning_selection_id: scenario for scenario in evaluation.scenarios}
    assert by_winner[A].gross_profit == Decimal("22")
    assert by_winner[A].commission == Decimal("0")
    assert by_winner[A].net_profit == Decimal("22")
    assert by_winner[B].gross_profit == Decimal("10")
    assert by_winner[B].commission == Decimal("2.20")
    assert by_winner[B].net_profit == Decimal("7.80")
    assert evaluation.total_lay_liability == Decimal("198.0")
    assert evaluation.guaranteed_profit == Decimal("7.80")
    assert evaluation.is_arbitrage


def test_two_opposing_lays_apply_commission_to_net_market_winnings_not_each_leg() -> None:
    lay_a = ExchangeStake(
        price=_exchange_price(selection_id=A, side=ExchangeSide.LAY, odds="1.9"),
        stake=Decimal("100"),
    )
    lay_b = ExchangeStake(
        price=_exchange_price(selection_id=B, side=ExchangeSide.LAY, odds="1.9"),
        stake=Decimal("100"),
    )

    evaluation = evaluate_exchange_portfolio(
        exchange_stakes=(lay_a, lay_b),
        expected_selection_ids=(A, B),
    )

    assert {scenario.gross_profit for scenario in evaluation.scenarios} == {Decimal("10.0")}
    assert {scenario.commission for scenario in evaluation.scenarios} == {Decimal("0.200")}
    assert {scenario.net_profit for scenario in evaluation.scenarios} == {Decimal("9.800")}
    assert evaluation.total_lay_liability == Decimal("180.0")
    assert evaluation.guaranteed_profit == Decimal("9.800")
    assert evaluation.is_arbitrage


def test_one_commission_scope_cannot_mix_conflicting_account_rates() -> None:
    lay_a = ExchangeStake(
        price=_exchange_price(selection_id=A, side=ExchangeSide.LAY, commission="0.02"),
        stake=Decimal("10"),
    )
    lay_b = ExchangeStake(
        price=_exchange_price(selection_id=B, side=ExchangeSide.LAY, commission="0.03"),
        stake=Decimal("10"),
    )

    _expect_math_error(
        lambda: evaluate_exchange_portfolio(
            exchange_stakes=(lay_a, lay_b),
            expected_selection_ids=(A, B),
        ),
        contains="conflicting commission rates",
    )


def test_exchange_transport_provenance_does_not_change_price_origin_identity() -> None:
    first = _exchange_price(selection_id=A, side=ExchangeSide.BACK)
    second = replace(
        first,
        transport_provider_id=ProviderId("provider:phase17-12:other-feed"),
    )

    assert first.exchange_provider.id == second.exchange_provider.id
    assert first.transport_provider_id != second.transport_provider_id
