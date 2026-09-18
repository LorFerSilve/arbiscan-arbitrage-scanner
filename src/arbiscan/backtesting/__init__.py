"""Historical analysis, replay, and backtesting API."""

from arbiscan.backtesting.models import (
    BacktestConfig,
    BacktestReport,
    BacktestSummary,
    HistoricalQuoteBatch,
    HistoricalQuoteCorpus,
    LatencySensitivityPoint,
    MatchingLabel,
    MatchingQualityMetrics,
    OpportunityInterval,
    ProviderReplayMetrics,
    ReplayDetection,
    StaleFalsePositive,
)
from arbiscan.backtesting.replay import (
    evaluate_matching_quality,
    run_backtest,
    run_latency_sensitivity,
)

__all__ = [
    "BacktestConfig",
    "BacktestReport",
    "BacktestSummary",
    "HistoricalQuoteBatch",
    "HistoricalQuoteCorpus",
    "LatencySensitivityPoint",
    "MatchingLabel",
    "MatchingQualityMetrics",
    "OpportunityInterval",
    "ProviderReplayMetrics",
    "ReplayDetection",
    "StaleFalsePositive",
    "evaluate_matching_quality",
    "run_backtest",
    "run_latency_sensitivity",
]
