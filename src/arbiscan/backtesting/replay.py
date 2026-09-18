"""Deterministic offline replay over canonical historical quote streams."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from arbiscan.arbitrage import build_opportunity, evaluate_market
from arbiscan.backtesting.models import (
    BacktestConfig,
    BacktestReport,
    BacktestSummary,
    HistoricalQuoteCorpus,
    LatencySensitivityPoint,
    MatchingLabel,
    MatchingQualityMetrics,
    OpportunityInterval,
    ProviderReplayMetrics,
    ReplayDetection,
    StaleFalsePositive,
    _OpenOpportunityInterval,
)
from arbiscan.domain import MarketId, OpportunityId, ProviderId, StakePlanId
from arbiscan.ingestion.realtime import QuoteKey
from arbiscan.lifecycle import LifecycleState, revalidate_opportunity
from arbiscan.marketbook import ProviderBookPolicy, build_market_books, quote_effective_timestamp
from arbiscan.matching import CanonicalRegistry

_METRIC_CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)
_ZERO = Decimal("0")


def _market_scope(
    registry: CanonicalRegistry,
    config: BacktestConfig,
) -> tuple[MarketId, ...]:
    if config.market_ids is None:
        return tuple(sorted((market.id for market in registry.markets), key=lambda value: value.value))

    unknown = tuple(
        market_id for market_id in config.market_ids if registry.market(market_id) is None
    )
    if unknown:
        raise ValueError(
            "backtest market_ids contain unknown canonical markets: "
            + ", ".join(value.value for value in unknown)
        )
    return config.market_ids


def _opportunity_id(market_id: MarketId, detected_at: object) -> OpportunityId:
    return OpportunityId(f"backtest|{market_id.value}|{detected_at}")


def _stake_plan_id(market_id: MarketId, detected_at: object) -> StakePlanId:
    return StakePlanId(f"backtest-plan|{market_id.value}|{detected_at}")


def _allowed_provider_ids(
    corpus: HistoricalQuoteCorpus,
    policy: ProviderBookPolicy | None,
) -> tuple[ProviderId, ...]:
    if policy is None:
        return corpus.providers
    return tuple(provider_id for provider_id in corpus.providers if policy.allows(provider_id))


def _counterfactual_freshness_window(
    current_quotes: tuple[object, ...],
    *,
    detected_at: object,
    minimum_window: timedelta,
) -> timedelta:
    # Types are intentionally checked by callers; this helper only derives a wide
    # enough finite window to include every currently available latest quote.
    available_ages: list[timedelta] = []
    for raw_quote in current_quotes:
        quote = raw_quote
        effective = quote_effective_timestamp(quote)  # type: ignore[arg-type]
        if effective <= detected_at and quote.ingested_at <= detected_at:  # type: ignore[attr-defined,operator]
            available_ages.append(detected_at - effective)  # type: ignore[operator]
    if not available_ages:
        return minimum_window
    oldest_age = max(available_ages)
    return max(minimum_window, oldest_age + timedelta(microseconds=1))


def _provider_only_policy(provider_id: ProviderId) -> ProviderBookPolicy:
    return ProviderBookPolicy(included_provider_ids=(provider_id,))


def _close_interval(
    state: _OpenOpportunityInterval,
    *,
    ended_at: object,
    closed_by_end_of_stream: bool,
) -> OpportunityInterval:
    return OpportunityInterval(
        event_id=state.event_id,
        market_id=state.market_id,
        started_at=state.started_at,
        ended_at=ended_at,  # type: ignore[arg-type]
        detection_count=state.detection_count,
        max_theoretical_profit_margin=state.max_margin,
        ever_actionable=state.ever_actionable,
        closed_by_end_of_stream=closed_by_end_of_stream,
    )


def run_backtest(
    corpus: HistoricalQuoteCorpus,
    *,
    registry: CanonicalRegistry,
    config: BacktestConfig,
) -> BacktestReport:
    """Replay one fixed canonical quote corpus through production detection primitives.

    The report measures detector behavior under explicit freshness, latency, provider,
    and optional actionability assumptions. It does not infer realized wagering profit.
    """

    if not isinstance(corpus, HistoricalQuoteCorpus):
        raise ValueError("corpus must be HistoricalQuoteCorpus")
    if not isinstance(registry, CanonicalRegistry):
        raise ValueError("registry must be CanonicalRegistry")
    if not isinstance(config, BacktestConfig):
        raise ValueError("config must be BacktestConfig")

    market_scope = _market_scope(registry, config)
    detection_times = tuple(
        sorted({batch.observed_at + config.detection_latency for batch in corpus.batches})
    )

    current_by_key: dict[QuoteKey, object] = {}
    next_batch = 0
    detections: list[ReplayDetection] = []
    stale_false_positives: list[StaleFalsePositive] = []
    intervals: list[OpportunityInterval] = []
    open_intervals: dict[MarketId, _OpenOpportunityInterval] = {}

    observed_counts: dict[ProviderId, int] = {provider_id: 0 for provider_id in corpus.providers}
    selected_best_counts: dict[ProviderId, int] = {
        provider_id: 0 for provider_id in corpus.providers
    }
    provider_complete_books: dict[ProviderId, int] = {
        provider_id: 0 for provider_id in corpus.providers
    }
    provider_theoretical: dict[ProviderId, int] = {
        provider_id: 0 for provider_id in corpus.providers
    }
    provider_actionable: dict[ProviderId, int] = {
        provider_id: 0 for provider_id in corpus.providers
    }

    for batch in corpus.batches:
        for quote in batch.quotes:
            observed_counts[quote.provider_id] = observed_counts.get(quote.provider_id, 0) + 1

    allowed_providers = _allowed_provider_ids(corpus, config.provider_policy)
    evaluation_count = 0

    for detected_at in detection_times:
        while (
            next_batch < len(corpus.batches)
            and corpus.batches[next_batch].observed_at <= detected_at
        ):
            batch = corpus.batches[next_batch]
            for quote in batch.quotes:
                current_by_key[QuoteKey.from_quote(quote)] = quote
            next_batch += 1

        current_quotes = tuple(current_by_key.values())
        strict_batch = build_market_books(
            current_quotes,
            registry=registry,
            as_of=detected_at,
            freshness_window=config.freshness_window,
            provider_policy=config.provider_policy,
            market_ids=market_scope,
        )

        strict_arbitrage_by_market: dict[MarketId, ReplayDetection] = {}
        for book in strict_batch.books:
            evaluation_count += 1
            for quote in book.quotes:
                selected_best_counts[quote.provider_id] = (
                    selected_best_counts.get(quote.provider_id, 0) + 1
                )

            evaluation = evaluate_market(
                book.quotes,
                book.expected_selection_ids,
                minimum_profit_margin=config.minimum_profit_margin,
            )
            if not evaluation.is_arbitrage:
                continue

            opportunity = build_opportunity(
                evaluation,
                opportunity_id=_opportunity_id(book.market.id, detected_at.isoformat()),
                detected_at=detected_at,
            )
            lifecycle = None
            if config.actionability_policy is not None:
                lifecycle = revalidate_opportunity(
                    opportunity,
                    book.quotes,
                    now=detected_at,
                    stake_plan_id=_stake_plan_id(book.market.id, detected_at.isoformat()),
                    policy=config.actionability_policy,
                )

            detection = ReplayDetection(
                detected_at=detected_at,
                opportunity=opportunity,
                evaluation=evaluation,
                lifecycle=lifecycle,
                selected_provider_ids=tuple({quote.provider_id for quote in book.quotes}),
                max_quote_age=max(
                    detected_at - quote_effective_timestamp(quote) for quote in book.quotes
                ),
            )
            detections.append(detection)
            strict_arbitrage_by_market[book.market.id] = detection

        relaxed_window = _counterfactual_freshness_window(
            current_quotes,
            detected_at=detected_at,
            minimum_window=config.freshness_window,
        )
        if relaxed_window > config.freshness_window:
            relaxed_batch = build_market_books(
                current_quotes,
                registry=registry,
                as_of=detected_at,
                freshness_window=relaxed_window,
                provider_policy=config.provider_policy,
                market_ids=market_scope,
            )
            for book in relaxed_batch.books:
                if book.market.id in strict_arbitrage_by_market:
                    continue
                evaluation = evaluate_market(
                    book.quotes,
                    book.expected_selection_ids,
                    minimum_profit_margin=config.minimum_profit_margin,
                )
                if not evaluation.is_arbitrage:
                    continue
                stale_false_positives.append(
                    StaleFalsePositive(
                        detected_at=detected_at,
                        event_id=book.event.id,
                        market_id=book.market.id,
                        counterfactual_profit_margin=evaluation.theoretical_profit_margin,
                        max_quote_age=max(
                            detected_at - quote_effective_timestamp(quote)
                            for quote in book.quotes
                        ),
                    )
                )

        for provider_id in allowed_providers:
            provider_batch = build_market_books(
                current_quotes,
                registry=registry,
                as_of=detected_at,
                freshness_window=config.freshness_window,
                provider_policy=_provider_only_policy(provider_id),
                market_ids=market_scope,
            )
            provider_complete_books[provider_id] = (
                provider_complete_books.get(provider_id, 0) + len(provider_batch.books)
            )
            for book in provider_batch.books:
                evaluation = evaluate_market(
                    book.quotes,
                    book.expected_selection_ids,
                    minimum_profit_margin=config.minimum_profit_margin,
                )
                if not evaluation.is_arbitrage:
                    continue
                provider_theoretical[provider_id] = (
                    provider_theoretical.get(provider_id, 0) + 1
                )
                if config.actionability_policy is None:
                    continue
                opportunity = build_opportunity(
                    evaluation,
                    opportunity_id=OpportunityId(
                        f"backtest-provider|{provider_id.value}|"
                        f"{book.market.id.value}|{detected_at.isoformat()}"
                    ),
                    detected_at=detected_at,
                )
                lifecycle = revalidate_opportunity(
                    opportunity,
                    book.quotes,
                    now=detected_at,
                    stake_plan_id=StakePlanId(
                        f"backtest-provider-plan|{provider_id.value}|"
                        f"{book.market.id.value}|{detected_at.isoformat()}"
                    ),
                    policy=config.actionability_policy,
                )
                if lifecycle.state is LifecycleState.ACTIONABLE:
                    provider_actionable[provider_id] = (
                        provider_actionable.get(provider_id, 0) + 1
                    )

        active_markets = set(strict_arbitrage_by_market)
        for market_id in tuple(open_intervals):
            if market_id in active_markets:
                continue
            intervals.append(
                _close_interval(
                    open_intervals.pop(market_id),
                    ended_at=detected_at,
                    closed_by_end_of_stream=False,
                )
            )

        for market_id, detection in strict_arbitrage_by_market.items():
            state = open_intervals.get(market_id)
            if state is None:
                open_intervals[market_id] = _OpenOpportunityInterval(
                    event_id=detection.evaluation.event_id,
                    market_id=market_id,
                    started_at=detected_at,
                    last_detected_at=detected_at,
                    detection_count=1,
                    max_margin=detection.evaluation.theoretical_profit_margin,
                    ever_actionable=detection.actionable,
                )
                continue
            state.last_detected_at = detected_at
            state.detection_count += 1
            state.max_margin = max(
                state.max_margin,
                detection.evaluation.theoretical_profit_margin,
            )
            state.ever_actionable = state.ever_actionable or detection.actionable

    final_time = detection_times[-1]
    for market_id in sorted(open_intervals, key=lambda value: value.value):
        intervals.append(
            _close_interval(
                open_intervals[market_id],
                ended_at=final_time,
                closed_by_end_of_stream=True,
            )
        )

    detections_tuple = tuple(
        sorted(
            detections,
            key=lambda item: (
                item.detected_at,
                item.evaluation.event_id.value,
                item.evaluation.market_id.value,
            ),
        )
    )
    intervals_tuple = tuple(
        sorted(
            intervals,
            key=lambda item: (
                item.started_at,
                item.event_id.value,
                item.market_id.value,
            ),
        )
    )
    stale_tuple = tuple(
        sorted(
            stale_false_positives,
            key=lambda item: (
                item.detected_at,
                item.event_id.value,
                item.market_id.value,
            ),
        )
    )

    provider_metrics = tuple(
        ProviderReplayMetrics(
            provider_id=provider_id,
            observed_quote_count=observed_counts.get(provider_id, 0),
            selected_best_quote_count=selected_best_counts.get(provider_id, 0),
            complete_book_count=provider_complete_books.get(provider_id, 0),
            theoretical_detection_count=provider_theoretical.get(provider_id, 0),
            actionable_detection_count=provider_actionable.get(provider_id, 0),
        )
        for provider_id in corpus.providers
    )

    total_duration = sum(
        (interval.duration for interval in intervals_tuple),
        timedelta(0),
    )
    actionable_count = sum(1 for detection in detections_tuple if detection.actionable)
    summary = BacktestSummary(
        corpus_digest=corpus.digest,
        detection_latency=config.detection_latency,
        evaluation_count=evaluation_count,
        theoretical_detection_count=len(detections_tuple),
        actionable_detection_count=actionable_count,
        stale_false_positive_count=len(stale_tuple),
        opportunity_interval_count=len(intervals_tuple),
        total_opportunity_duration=total_duration,
        actionability_evaluated=config.actionability_policy is not None,
    )
    return BacktestReport(
        summary=summary,
        detections=detections_tuple,
        opportunity_intervals=intervals_tuple,
        stale_false_positives=stale_tuple,
        provider_metrics=provider_metrics,
    )


def run_latency_sensitivity(
    corpus: HistoricalQuoteCorpus,
    *,
    registry: CanonicalRegistry,
    base_config: BacktestConfig,
    latencies: tuple[timedelta, ...],
) -> tuple[LatencySensitivityPoint, ...]:
    """Replay one fixed corpus under multiple detector delays."""

    if not latencies:
        raise ValueError("latencies cannot be empty")
    if any(not isinstance(value, timedelta) or value < timedelta(0) for value in latencies):
        raise ValueError("latencies must contain non-negative timedelta values")
    if len(set(latencies)) != len(latencies):
        raise ValueError("latencies must be unique")

    points: list[LatencySensitivityPoint] = []
    for latency in sorted(latencies):
        report = run_backtest(
            corpus,
            registry=registry,
            config=replace(base_config, detection_latency=latency),
        )
        points.append(
            LatencySensitivityPoint(
                latency=latency,
                theoretical_detection_count=report.summary.theoretical_detection_count,
                actionable_detection_count=report.summary.actionable_detection_count,
                stale_false_positive_count=report.summary.stale_false_positive_count,
                opportunity_interval_count=report.summary.opportunity_interval_count,
                total_opportunity_duration=report.summary.total_opportunity_duration,
            )
        )
    return tuple(points)


def evaluate_matching_quality(
    labels: tuple[MatchingLabel, ...],
) -> MatchingQualityMetrics:
    """Return precision/recall for labeled canonical event-matching decisions.

    A wrong non-null prediction counts as both a false positive for the predicted
    identity and a false negative for the expected identity.
    """

    values = tuple(labels)
    if not values:
        raise ValueError("matching labels cannot be empty")
    if any(not isinstance(value, MatchingLabel) for value in values):
        raise ValueError("labels must contain MatchingLabel values")
    source_ids = [value.source_record_id for value in values]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("matching labels must have unique source_record_id values")

    true_positive = 0
    false_positive = 0
    false_negative = 0
    for label in values:
        expected = label.expected_event_id
        predicted = label.predicted_event_id
        if expected is not None and predicted == expected:
            true_positive += 1
            continue
        if predicted is not None:
            false_positive += 1
        if expected is not None:
            false_negative += 1

    with localcontext(_METRIC_CONTEXT):
        precision_denominator = true_positive + false_positive
        recall_denominator = true_positive + false_negative
        precision = (
            _ZERO
            if precision_denominator == 0
            else Decimal(true_positive) / Decimal(precision_denominator)
        )
        recall = (
            _ZERO
            if recall_denominator == 0
            else Decimal(true_positive) / Decimal(recall_denominator)
        )

    return MatchingQualityMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
    )
