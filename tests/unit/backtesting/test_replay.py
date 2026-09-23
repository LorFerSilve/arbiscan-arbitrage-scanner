"""Phase 18 deterministic historical replay and analysis regressions."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.arbitrage import CurrencyRoundingPolicy
from arbiscan.backtesting import (
    BacktestConfig,
    HistoricalQuoteCorpus,
    MatchingLabel,
    evaluate_matching_quality,
    run_backtest,
    run_latency_sensitivity,
)
from arbiscan.domain import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventStatus,
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    OddsQuote,
    Participant,
    ParticipantId,
    ParticipantKind,
    ProviderId,
    QuoteId,
    QuoteStatus,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
)
from arbiscan.lifecycle import ActionabilityPolicy, LifecycleState
from arbiscan.matching import CanonicalRegistry
from arbiscan.services.realtime_scanner import RealtimeScanner

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
EVENT_ID = EventId("event:phase18")
MARKET_ID = MarketId("market:phase18:total")
OVER = SelectionId("selection:phase18:over")
UNDER = SelectionId("selection:phase18:under")
P1 = ProviderId("provider:phase18:one")
P2 = ProviderId("provider:phase18:two")


def _registry() -> CanonicalRegistry:
    competition = Competition(
        id=CompetitionId("competition:phase18"),
        sport=Sport.FOOTBALL,
        name="Phase 18 League",
        region="BE",
        season="2026",
    )
    participants = (
        Participant(
            id=ParticipantId("participant:phase18:a"),
            sport=Sport.FOOTBALL,
            name="A",
            kind=ParticipantKind.TEAM,
        ),
        Participant(
            id=ParticipantId("participant:phase18:b"),
            sport=Sport.FOOTBALL,
            name="B",
            kind=ParticipantKind.TEAM,
        ),
    )
    event = Event(
        id=EVENT_ID,
        sport=Sport.FOOTBALL,
        competition=competition,
        participants=participants,
        scheduled_start=T0 + timedelta(hours=2),
        status=EventStatus.SCHEDULED,
    )
    market = Market(
        id=MARKET_ID,
        event_id=EVENT_ID,
        kind=MarketKind.TOTAL_POINTS,
        period=MarketPeriod.REGULATION,
        line=Decimal("2.5"),
    )
    selections = (
        Selection(id=OVER, market_id=MARKET_ID, kind=SelectionKind.OVER),
        Selection(id=UNDER, market_id=MARKET_ID, kind=SelectionKind.UNDER),
    )
    return CanonicalRegistry(
        competitions=(competition,),
        participants=participants,
        events=(event,),
        markets=(market,),
        selections=selections,
    )


def _refundable_registry() -> CanonicalRegistry:
    """The same football event with a Draw No Bet / handicap-zero market."""
    base = _registry()
    return CanonicalRegistry(
        competitions=base.competitions,
        participants=base.participants,
        events=base.events,
        markets=(replace(base.markets[0], kind=MarketKind.HANDICAP, line=Decimal("0")),),
        selections=(
            replace(
                base.selections[0],
                kind=SelectionKind.PARTICIPANT,
                participant_id=base.participants[0].id,
                handicap=Decimal("0"),
            ),
            replace(
                base.selections[1],
                kind=SelectionKind.PARTICIPANT,
                participant_id=base.participants[1].id,
                handicap=Decimal("0"),
            ),
        ),
    )


def _quote(
    provider_id: ProviderId,
    selection_id: SelectionId,
    odds: str,
    *,
    at: datetime,
    revision: int,
) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(
            f"quote:phase18:{provider_id.value.rsplit(':', 1)[-1]}:"
            f"{selection_id.value.rsplit(':', 1)[-1]}:{revision}"
        ),
        provider_id=provider_id,
        event_id=EVENT_ID,
        market_id=MARKET_ID,
        selection_id=selection_id,
        decimal_price=Decimal(odds),
        source_event_id="source:event:phase18",
        source_market_id="source:market:phase18",
        source_selection_id=selection_id.value,
        source_timestamp=at,
        ingested_at=at,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{provider_id.value}:{selection_id.value}:{revision}",
    )


def _actionability_policy() -> ActionabilityPolicy:
    return ActionabilityPolicy(
        bankroll=Decimal("100"),
        rounding_policy=CurrencyRoundingPolicy(currency="EUR"),
        maximum_quote_age_seconds=Decimal("30"),
    )


def test_replay_reproduces_theoretical_and_actionable_lifecycle_duration() -> None:
    quotes = (
        _quote(P1, OVER, "2.20", at=T0, revision=1),
        _quote(P2, UNDER, "2.20", at=T0, revision=1),
        _quote(P1, OVER, "1.80", at=T0 + timedelta(seconds=10), revision=2),
    )
    corpus = HistoricalQuoteCorpus.from_quotes(quotes)
    report = run_backtest(
        corpus,
        registry=_registry(),
        config=BacktestConfig(
            freshness_window=timedelta(seconds=30),
            actionability_policy=_actionability_policy(),
        ),
    )

    assert report.summary.evaluation_count == 2
    assert report.summary.theoretical_detection_count == 1
    assert report.summary.actionable_detection_count == 1
    assert report.summary.opportunity_interval_count == 1
    assert report.summary.total_opportunity_duration == timedelta(seconds=10)
    assert report.summary.actionability_evaluated
    assert report.detections[0].lifecycle is not None
    assert report.detections[0].lifecycle.state is LifecycleState.ACTIONABLE

    interval = report.opportunity_intervals[0]
    assert interval.started_at == T0
    assert interval.ended_at == T0 + timedelta(seconds=10)
    assert interval.detection_count == 1
    assert interval.ever_actionable
    assert not interval.closed_by_end_of_stream

    # The same fixed corpus must remain byte-identifiable across repeated construction.
    assert corpus.digest == HistoricalQuoteCorpus.from_quotes(quotes).digest


def test_latency_sensitivity_can_remove_short_lived_opportunity() -> None:
    corpus = HistoricalQuoteCorpus.from_quotes(
        (
            _quote(P1, OVER, "2.20", at=T0, revision=1),
            _quote(P2, UNDER, "2.20", at=T0, revision=1),
            _quote(P1, OVER, "1.80", at=T0 + timedelta(seconds=5), revision=2),
        )
    )
    points = run_latency_sensitivity(
        corpus,
        registry=_registry(),
        base_config=BacktestConfig(freshness_window=timedelta(seconds=30)),
        latencies=(timedelta(0), timedelta(seconds=10)),
    )

    assert points[0].latency == timedelta(0)
    assert points[0].theoretical_detection_count == 1
    assert points[1].latency == timedelta(seconds=10)
    assert points[1].theoretical_detection_count == 0


def test_stale_counterfactual_quantifies_false_positive_signal() -> None:
    corpus = HistoricalQuoteCorpus.from_quotes(
        (
            _quote(P1, OVER, "2.20", at=T0, revision=1),
            _quote(P2, UNDER, "2.20", at=T0, revision=1),
            _quote(P2, UNDER, "2.30", at=T0 + timedelta(seconds=31), revision=2),
        )
    )
    report = run_backtest(
        corpus,
        registry=_registry(),
        config=BacktestConfig(freshness_window=timedelta(seconds=30)),
    )

    assert report.summary.stale_false_positive_count == 1
    stale = report.stale_false_positives[0]
    assert stale.detected_at == T0 + timedelta(seconds=31)
    assert stale.market_id == MARKET_ID
    assert stale.max_quote_age == timedelta(seconds=31)
    assert stale.counterfactual_profit_margin > Decimal("0")


def test_provider_metrics_compare_standalone_book_coverage_and_signal() -> None:
    corpus = HistoricalQuoteCorpus.from_quotes(
        (
            _quote(P1, OVER, "2.05", at=T0, revision=1),
            _quote(P1, UNDER, "2.05", at=T0, revision=1),
            _quote(P2, OVER, "1.90", at=T0, revision=1),
            _quote(P2, UNDER, "1.90", at=T0, revision=1),
        )
    )
    report = run_backtest(
        corpus,
        registry=_registry(),
        config=BacktestConfig(freshness_window=timedelta(seconds=30)),
    )
    by_provider = {metric.provider_id: metric for metric in report.provider_metrics}

    assert by_provider[P1].observed_quote_count == 2
    assert by_provider[P1].selected_best_quote_count == 2
    assert by_provider[P1].complete_book_count == 1
    assert by_provider[P1].theoretical_detection_count == 1

    assert by_provider[P2].observed_quote_count == 2
    assert by_provider[P2].selected_best_quote_count == 0
    assert by_provider[P2].complete_book_count == 1
    assert by_provider[P2].theoretical_detection_count == 0


def test_refundable_market_cannot_enter_generic_replay_or_live_scope() -> None:
    registry = _refundable_registry()
    corpus = HistoricalQuoteCorpus.from_quotes(
        (
            _quote(P1, OVER, "2.20", at=T0, revision=1),
            _quote(P2, UNDER, "2.20", at=T0, revision=1),
        )
    )
    report = run_backtest(
        corpus,
        registry=registry,
        config=BacktestConfig(freshness_window=timedelta(seconds=30)),
    )

    assert report.summary.evaluation_count == 0
    assert report.summary.theoretical_detection_count == 0
    assert report.summary.stale_false_positive_count == 0
    assert all(metric.theoretical_detection_count == 0 for metric in report.provider_metrics)
    assert (
        RealtimeScanner(adapters=(), registry=registry, sport=Sport.FOOTBALL)._market_scope() == ()
    )

    try:
        run_backtest(
            corpus,
            registry=registry,
            config=BacktestConfig(freshness_window=timedelta(seconds=30), market_ids=(MARKET_ID,)),
        )
    except ValueError as error:
        assert "unsupported by generic arbitrage" in str(error)
    else:
        raise AssertionError("explicit refundable market scope must fail closed")


def test_replay_consolidates_same_bookmaker_feeds_before_price_selection() -> None:
    first = replace(
        _quote(P1, OVER, "2.20", at=T0, revision=1),
        transport_provider_id=ProviderId("transport:a"),
    )
    second = replace(
        first,
        id=QuoteId("quote:phase18:over:second-feed"),
        transport_provider_id=ProviderId("transport:b"),
    )
    under = _quote(P2, UNDER, "2.20", at=T0, revision=1)
    config = BacktestConfig(freshness_window=timedelta(seconds=30))

    equivalent = run_backtest(
        HistoricalQuoteCorpus.from_quotes((first, second, under)),
        registry=_registry(),
        config=config,
    )
    assert equivalent.summary.theoretical_detection_count == 1
    assert first.id in equivalent.detections[0].opportunity.quote_ids
    assert second.id not in equivalent.detections[0].opportunity.quote_ids

    conflict = run_backtest(
        HistoricalQuoteCorpus.from_quotes(
            (first, replace(second, decimal_price=Decimal("2.40")), under)
        ),
        registry=_registry(),
        config=config,
    )
    assert conflict.summary.theoretical_detection_count == 0
    assert conflict.summary.stale_false_positive_count == 0
    assert all(metric.theoretical_detection_count == 0 for metric in conflict.provider_metrics)


def test_replay_rejects_out_of_order_source_update_like_live_store() -> None:
    old_update = replace(
        _quote(P1, OVER, "1.20", at=T0 + timedelta(seconds=10), revision=2),
        source_timestamp=T0 - timedelta(seconds=60),
    )
    corpus = HistoricalQuoteCorpus.from_quotes(
        (
            _quote(P1, OVER, "2.20", at=T0, revision=1),
            _quote(P2, UNDER, "2.20", at=T0, revision=1),
            old_update,
        )
    )
    report = run_backtest(
        corpus,
        registry=_registry(),
        config=BacktestConfig(freshness_window=timedelta(seconds=120)),
    )

    assert report.summary.theoretical_detection_count == 2
    assert all(
        old_update.id not in detection.opportunity.quote_ids for detection in report.detections
    )


def test_matching_precision_recall_counts_wrong_identity_as_fp_and_fn() -> None:
    e1 = EventId("event:labeled:1")
    e2 = EventId("event:labeled:2")
    e3 = EventId("event:labeled:3")
    e4 = EventId("event:labeled:4")
    e5 = EventId("event:labeled:5")

    metrics = evaluate_matching_quality(
        (
            MatchingLabel("source:1", expected_event_id=e1, predicted_event_id=e1),
            MatchingLabel("source:2", expected_event_id=None, predicted_event_id=e2),
            MatchingLabel("source:3", expected_event_id=e3, predicted_event_id=None),
            MatchingLabel("source:4", expected_event_id=e4, predicted_event_id=e5),
        )
    )

    assert metrics.true_positive == 1
    assert metrics.false_positive == 2
    assert metrics.false_negative == 2
    expected_third = Decimal("0." + ("3" * 60))
    assert metrics.precision == expected_third
    assert metrics.recall == expected_third
