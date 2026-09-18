"""Pure provider-independent arbitrage mathematics API."""

from arbiscan.arbitrage.core import (
    MATH_PRECISION,
    build_opportunity,
    evaluate_market,
    gross_return_multiplier,
    implied_probability,
    implied_probability_sum,
    is_theoretical_arbitrage,
    theoretical_profit_margin,
)
from arbiscan.arbitrage.exchange import (
    BookmakerBackStake,
    ExchangePortfolioEvaluation,
    ExchangePriceObservation,
    ExchangePriceSupportDecision,
    ExchangeScenarioProfit,
    ExchangeSide,
    ExchangeStake,
    assess_exchange_price_support,
    evaluate_exchange_portfolio,
    lay_liability,
)
from arbiscan.arbitrage.errors import (
    ArbitrageMathError,
    IncompleteMarketError,
    StakeConstraintError,
)
from arbiscan.arbitrage.models import (
    ArbitrageEvaluation,
    CurrencyRoundingPolicy,
    RefundableTwoWayEvaluation,
    StakeConstraint,
)
from arbiscan.arbitrage.refundable import evaluate_refundable_two_way_market
from arbiscan.arbitrage.staking import allocate_stakes

__all__ = [
    "MATH_PRECISION",
    "ArbitrageEvaluation",
    "ArbitrageMathError",
    "BookmakerBackStake",
    "CurrencyRoundingPolicy",
    "ExchangePortfolioEvaluation",
    "ExchangePriceObservation",
    "ExchangePriceSupportDecision",
    "ExchangeScenarioProfit",
    "ExchangeSide",
    "ExchangeStake",
    "IncompleteMarketError",
    "RefundableTwoWayEvaluation",
    "StakeConstraint",
    "StakeConstraintError",
    "allocate_stakes",
    "assess_exchange_price_support",
    "build_opportunity",
    "evaluate_exchange_portfolio",
    "evaluate_market",
    "evaluate_refundable_two_way_market",
    "gross_return_multiplier",
    "implied_probability",
    "implied_probability_sum",
    "is_theoretical_arbitrage",
    "lay_liability",
    "theoretical_profit_margin",
]
