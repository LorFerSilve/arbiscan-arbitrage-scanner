"""Settlement-aware exchange back/lay mathematics and safety gates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum

from arbiscan.arbitrage.errors import ArbitrageMathError
from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    Provider,
    ProviderId,
    ProviderKind,
    QuoteStatus,
    SelectionId,
)

_EXCHANGE_CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)
_ZERO = Decimal("0")
_ONE = Decimal("1")


class ExchangeSide(StrEnum):
    """Exchange order side; BACK and LAY have different terminal-state payouts."""

    BACK = "back"
    LAY = "lay"


@dataclass(frozen=True, slots=True)
class ExchangePriceObservation:
    """Provider-independent exchange price before stake materialization.

    Optional side, liquidity, commission, and commission-scope fields intentionally
    permit an adapter to retain an incomplete source observation. Such an observation
    cannot be used by the exchange arbitrage evaluator until the explicit support gate
    proves every required term.
    """

    exchange_provider: Provider
    transport_provider_id: ProviderId
    event_id: EventId
    market_id: MarketId
    selection_id: SelectionId
    decimal_price: Decimal
    status: QuoteStatus = QuoteStatus.ACTIVE
    side: ExchangeSide | None = None
    available_stake: Decimal | None = None
    commission_rate: Decimal | None = None
    commission_scope: str | None = None
    settlement_rules_verified: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.exchange_provider, Provider):
            raise ArbitrageMathError("exchange_price.exchange_provider must be Provider")
        if self.exchange_provider.kind is not ProviderKind.EXCHANGE:
            raise ArbitrageMathError("exchange price origin must have ProviderKind.EXCHANGE")
        if not isinstance(self.transport_provider_id, ProviderId):
            raise ArbitrageMathError("exchange_price.transport_provider_id must be ProviderId")
        if not isinstance(self.event_id, EventId):
            raise ArbitrageMathError("exchange_price.event_id must be EventId")
        if not isinstance(self.market_id, MarketId):
            raise ArbitrageMathError("exchange_price.market_id must be MarketId")
        if not isinstance(self.selection_id, SelectionId):
            raise ArbitrageMathError("exchange_price.selection_id must be SelectionId")
        if not isinstance(self.status, QuoteStatus):
            raise ArbitrageMathError("exchange_price.status must be QuoteStatus")
        if self.side is not None and not isinstance(self.side, ExchangeSide):
            raise ArbitrageMathError("exchange_price.side must be ExchangeSide when present")
        if type(self.settlement_rules_verified) is not bool:
            raise ArbitrageMathError("exchange_price.settlement_rules_verified must be bool")

        price = _require_decimal(self.decimal_price, field="exchange_price.decimal_price")
        if price <= _ONE:
            raise ArbitrageMathError("exchange_price.decimal_price must be greater than 1")
        object.__setattr__(self, "decimal_price", price)

        if self.available_stake is not None:
            available = _require_decimal(
                self.available_stake,
                field="exchange_price.available_stake",
            )
            if available <= _ZERO:
                raise ArbitrageMathError("exchange_price.available_stake must be positive")
            object.__setattr__(self, "available_stake", available)

        if self.commission_rate is not None:
            commission = _require_decimal(
                self.commission_rate,
                field="exchange_price.commission_rate",
            )
            if commission < _ZERO or commission >= _ONE:
                raise ArbitrageMathError(
                    "exchange_price.commission_rate must be in the interval [0, 1)"
                )
            object.__setattr__(self, "commission_rate", commission)

        if self.commission_scope is not None:
            if not isinstance(self.commission_scope, str) or not self.commission_scope.strip():
                raise ArbitrageMathError(
                    "exchange_price.commission_scope must be non-empty text when present"
                )
            object.__setattr__(self, "commission_scope", self.commission_scope.strip())


@dataclass(frozen=True, slots=True)
class ExchangePriceSupportDecision:
    """Whether one exchange price contains enough semantics for safe evaluation."""

    eligible: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExchangeStake:
    """Matched exchange stake at one explicit BACK or LAY price."""

    price: ExchangePriceObservation
    stake: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.price, ExchangePriceObservation):
            raise ArbitrageMathError("exchange_stake.price must be ExchangePriceObservation")
        decision = assess_exchange_price_support(self.price)
        if not decision.eligible:
            raise ArbitrageMathError(
                "exchange stake requires an eligible price; blockers="
                + ", ".join(decision.blockers)
            )
        stake = _require_decimal(self.stake, field="exchange_stake.stake")
        if stake <= _ZERO:
            raise ArbitrageMathError("exchange_stake.stake must be positive")
        available = self.price.available_stake
        if available is None:
            raise ArbitrageMathError("exchange stake requires available liquidity")
        if stake > available:
            raise ArbitrageMathError("exchange stake exceeds available matched liquidity")
        object.__setattr__(self, "stake", stake)

    @property
    def liability(self) -> Decimal:
        """Return lay liability, or the back stake itself for BACK exposure."""
        if self.price.side is ExchangeSide.LAY:
            return lay_liability(self.stake, self.price.decimal_price)
        return self.stake


@dataclass(frozen=True, slots=True)
class BookmakerBackStake:
    """One ordinary fixed-odds BACK stake used in a mixed bookmaker/exchange hedge."""

    quote: OddsQuote
    price_provider: Provider
    stake: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.quote, OddsQuote):
            raise ArbitrageMathError("bookmaker_back.quote must be OddsQuote")
        if not isinstance(self.price_provider, Provider):
            raise ArbitrageMathError("bookmaker_back.price_provider must be Provider")
        if self.price_provider.kind is not ProviderKind.BOOKMAKER:
            raise ArbitrageMathError("bookmaker back origin must have ProviderKind.BOOKMAKER")
        if self.price_provider.id != self.quote.provider_id:
            raise ArbitrageMathError(
                "bookmaker back provider metadata must match quote.provider_id"
            )
        if self.quote.status is not QuoteStatus.ACTIVE:
            raise ArbitrageMathError("bookmaker back quote must be active")
        stake = _require_decimal(self.stake, field="bookmaker_back.stake")
        if stake <= _ZERO:
            raise ArbitrageMathError("bookmaker_back.stake must be positive")
        object.__setattr__(self, "stake", stake)


@dataclass(frozen=True, slots=True)
class ExchangeScenarioProfit:
    """Net portfolio result when one canonical selection is the terminal winner."""

    winning_selection_id: SelectionId
    gross_profit: Decimal
    commission: Decimal
    net_profit: Decimal


@dataclass(frozen=True, slots=True)
class ExchangePortfolioEvaluation:
    """Scenario matrix for a portfolio containing at least one exchange leg."""

    event_id: EventId
    market_id: MarketId
    scenarios: tuple[ExchangeScenarioProfit, ...]
    total_lay_liability: Decimal
    guaranteed_profit: Decimal
    is_arbitrage: bool

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId):
            raise ArbitrageMathError("exchange evaluation event_id must be EventId")
        if not isinstance(self.market_id, MarketId):
            raise ArbitrageMathError("exchange evaluation market_id must be MarketId")
        scenarios = tuple(self.scenarios)
        if len(scenarios) < 2:
            raise ArbitrageMathError("exchange evaluation requires at least two scenarios")
        if any(not isinstance(value, ExchangeScenarioProfit) for value in scenarios):
            raise ArbitrageMathError(
                "exchange evaluation scenarios must contain ExchangeScenarioProfit values"
            )
        if len({value.winning_selection_id for value in scenarios}) != len(scenarios):
            raise ArbitrageMathError("exchange evaluation scenario selections must be unique")
        object.__setattr__(self, "scenarios", scenarios)

        liability = _require_decimal(
            self.total_lay_liability,
            field="exchange_evaluation.total_lay_liability",
        )
        guaranteed = _require_decimal(
            self.guaranteed_profit,
            field="exchange_evaluation.guaranteed_profit",
        )
        if liability < _ZERO:
            raise ArbitrageMathError("total lay liability cannot be negative")
        if guaranteed != min(value.net_profit for value in scenarios):
            raise ArbitrageMathError("guaranteed profit must equal the minimum scenario net profit")
        if self.is_arbitrage is not (guaranteed > _ZERO):
            raise ArbitrageMathError(
                "exchange arbitrage flag must reflect strictly positive guaranteed profit"
            )


def _require_decimal(value: object, *, field: str) -> Decimal:
    if type(value) is not Decimal:
        raise ArbitrageMathError(f"{field} must be Decimal")
    if not value.is_finite():
        raise ArbitrageMathError(f"{field} must be finite")
    return value


def assess_exchange_price_support(
    price: ExchangePriceObservation,
) -> ExchangePriceSupportDecision:
    """Fail closed when exchange side, liquidity, commission, or settlement is unknown."""

    if not isinstance(price, ExchangePriceObservation):
        raise ArbitrageMathError("price must be ExchangePriceObservation")

    blockers: list[str] = []
    if price.status is not QuoteStatus.ACTIVE:
        blockers.append("price is not active")
    if price.side is None:
        blockers.append("BACK/LAY side identity is missing")
    if price.available_stake is None:
        blockers.append("matched liquidity is missing")
    if price.commission_rate is None:
        blockers.append("commission rate is missing")
    if price.commission_scope is None:
        blockers.append("commission scope/account-market provenance is missing")
    if not price.settlement_rules_verified:
        blockers.append("settlement-rule equivalence is not verified")

    return ExchangePriceSupportDecision(eligible=not blockers, blockers=tuple(blockers))


def lay_liability(stake: Decimal, decimal_price: Decimal) -> Decimal:
    """Return the maximum losing liability of a matched lay stake."""

    stake_value = _require_decimal(stake, field="lay.stake")
    odds = _require_decimal(decimal_price, field="lay.decimal_price")
    if stake_value <= _ZERO:
        raise ArbitrageMathError("lay.stake must be positive")
    if odds <= _ONE:
        raise ArbitrageMathError("lay.decimal_price must be greater than 1")
    with localcontext(_EXCHANGE_CONTEXT):
        return stake_value * (odds - _ONE)


def evaluate_exchange_portfolio(
    *,
    bookmaker_backs: tuple[BookmakerBackStake, ...] = (),
    exchange_stakes: tuple[ExchangeStake, ...],
    expected_selection_ids: tuple[SelectionId, ...],
) -> ExchangePortfolioEvaluation:
    """Evaluate bookmaker BACK plus exchange BACK/LAY legs over every terminal outcome.

    Exchange commission is applied to positive *net market winnings* per
    exchange-provider/commission-scope group, never independently per winning leg.
    """

    bookmaker_values = tuple(bookmaker_backs)
    exchange_values = tuple(exchange_stakes)
    expected = tuple(expected_selection_ids)

    if not exchange_values:
        raise ArbitrageMathError("exchange portfolio requires at least one exchange stake")
    if len(expected) < 2 or len(set(expected)) != len(expected):
        raise ArbitrageMathError(
            "expected_selection_ids must contain at least two unique SelectionId values"
        )
    if any(not isinstance(value, SelectionId) for value in expected):
        raise ArbitrageMathError("expected_selection_ids must contain SelectionId values")
    if any(not isinstance(value, BookmakerBackStake) for value in bookmaker_values):
        raise ArbitrageMathError("bookmaker_backs must contain BookmakerBackStake values")
    if any(not isinstance(value, ExchangeStake) for value in exchange_values):
        raise ArbitrageMathError("exchange_stakes must contain ExchangeStake values")

    first_event = exchange_values[0].price.event_id
    first_market = exchange_values[0].price.market_id
    expected_set = set(expected)

    for exchange_leg in exchange_values:
        if (
            exchange_leg.price.event_id != first_event
            or exchange_leg.price.market_id != first_market
        ):
            raise ArbitrageMathError("all exchange legs must belong to one event and market")
        if exchange_leg.price.selection_id not in expected_set:
            raise ArbitrageMathError("exchange leg selection is outside the expected market")
    for bookmaker_leg in bookmaker_values:
        if (
            bookmaker_leg.quote.event_id != first_event
            or bookmaker_leg.quote.market_id != first_market
        ):
            raise ArbitrageMathError(
                "bookmaker and exchange legs must belong to one canonical event and market"
            )
        if bookmaker_leg.quote.selection_id not in expected_set:
            raise ArbitrageMathError("bookmaker leg selection is outside the expected market")

    commission_rates: dict[tuple[ProviderId, str], Decimal] = {}
    for exchange_leg in exchange_values:
        price = exchange_leg.price
        scope = price.commission_scope
        rate = price.commission_rate
        if scope is None or rate is None:
            raise ArbitrageMathError("eligible exchange stake lost commission semantics")
        key = (price.exchange_provider.id, scope)
        previous = commission_rates.get(key)
        if previous is not None and previous != rate:
            raise ArbitrageMathError(
                "one exchange commission scope cannot contain conflicting commission rates"
            )
        commission_rates[key] = rate

    scenarios: list[ExchangeScenarioProfit] = []
    for winner in sorted(expected, key=lambda value: value.value):
        bookmaker_profit = _ZERO
        exchange_gross: dict[tuple[ProviderId, str], Decimal] = {
            key: _ZERO for key in commission_rates
        }

        with localcontext(_EXCHANGE_CONTEXT):
            for bookmaker_leg in bookmaker_values:
                if bookmaker_leg.quote.selection_id == winner:
                    bookmaker_profit += bookmaker_leg.stake * (
                        bookmaker_leg.quote.decimal_price - _ONE
                    )
                else:
                    bookmaker_profit -= bookmaker_leg.stake

            for exchange_leg in exchange_values:
                price = exchange_leg.price
                side = price.side
                scope = price.commission_scope
                if side is None or scope is None:
                    raise ArbitrageMathError("eligible exchange stake lost side/scope semantics")
                key = (price.exchange_provider.id, scope)
                if side is ExchangeSide.BACK:
                    profit = (
                        exchange_leg.stake * (price.decimal_price - _ONE)
                        if price.selection_id == winner
                        else -exchange_leg.stake
                    )
                else:
                    profit = (
                        -lay_liability(exchange_leg.stake, price.decimal_price)
                        if price.selection_id == winner
                        else exchange_leg.stake
                    )
                exchange_gross[key] += profit

            commission = sum(
                (
                    gross * commission_rates[key]
                    for key, gross in exchange_gross.items()
                    if gross > _ZERO
                ),
                _ZERO,
            )
            gross_profit = bookmaker_profit + sum(exchange_gross.values(), _ZERO)
            net_profit = gross_profit - commission

        scenarios.append(
            ExchangeScenarioProfit(
                winning_selection_id=winner,
                gross_profit=gross_profit,
                commission=commission,
                net_profit=net_profit,
            )
        )

    total_lay_liability = sum(
        (
            exchange_leg.liability
            for exchange_leg in exchange_values
            if exchange_leg.price.side is ExchangeSide.LAY
        ),
        _ZERO,
    )
    guaranteed_profit = min(value.net_profit for value in scenarios)
    return ExchangePortfolioEvaluation(
        event_id=first_event,
        market_id=first_market,
        scenarios=tuple(scenarios),
        total_lay_liability=total_lay_liability,
        guaranteed_profit=guaranteed_profit,
        is_arbitrage=guaranteed_profit > _ZERO,
    )
