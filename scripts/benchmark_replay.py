"""Measure deterministic, in-process historical replay without provider or file I/O."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import timedelta
from hashlib import sha256
from time import perf_counter_ns

from arbiscan.backtesting import BacktestConfig, BacktestReport, HistoricalQuoteCorpus, run_backtest
from arbiscan.matching import CanonicalRegistry
from scripts.benchmark_detection import (
    START,
    _milliseconds,
    _non_negative_int,
    _observations,
    _positive_int,
    _workload,
)


def _corpus(
    *,
    events: int,
    markets_per_event: int,
    providers: int,
    update_batches: int,
    updates_per_batch: int,
    transports_per_provider: int,
    conflicting_slots: int,
) -> tuple[CanonicalRegistry, HistoricalQuoteCorpus, int]:
    if min(events, markets_per_event, providers, updates_per_batch, transports_per_provider) < 1:
        raise ValueError("workload dimensions must be positive")
    if update_batches < 0:
        raise ValueError("update_batches cannot be negative")

    registry, specs = _workload(
        events=events, markets_per_event=markets_per_event, providers=providers
    )
    if updates_per_batch > len(specs):
        raise ValueError("updates_per_batch cannot exceed initial quote count")
    if conflicting_slots < 0 or conflicting_slots > len(specs):
        raise ValueError("conflicting_slots must be between zero and initial quote count")
    if conflicting_slots and transports_per_provider < 2:
        raise ValueError("conflicting_slots requires at least two transports per provider")

    observations = [
        quote
        for spec_index, spec in enumerate(specs)
        for quote in _observations(
            spec,
            at=START,
            revision=0,
            transports_per_provider=transports_per_provider,
            conflicting=spec_index < conflicting_slots,
        )
    ]
    for batch_number in range(1, update_batches + 1):
        at = START + timedelta(seconds=batch_number)
        offset = (batch_number * updates_per_batch) % len(specs)
        observations.extend(
            quote
            for spec_index in range(offset, offset + updates_per_batch)
            for quote in _observations(
                specs[spec_index % len(specs)],
                at=at,
                revision=batch_number,
                transports_per_provider=transports_per_provider,
                conflicting=spec_index % len(specs) < conflicting_slots,
            )
        )
    return registry, HistoricalQuoteCorpus.from_quotes(tuple(observations)), len(specs)


def _report_signature(report: BacktestReport) -> str:
    """Hash explicit semantic fields, excluding runtime and object representations."""
    summary = report.summary
    payload = {
        "summary": [
            summary.detection_latency.total_seconds(),
            summary.evaluation_count,
            summary.theoretical_detection_count,
            summary.actionable_detection_count,
            summary.stale_false_positive_count,
            summary.opportunity_interval_count,
            summary.total_opportunity_duration.total_seconds(),
            summary.actionability_evaluated,
        ],
        "detections": [
            [
                detection.detected_at.isoformat(),
                detection.evaluation.market_id.value,
                [quote_id.value for quote_id in detection.opportunity.quote_ids],
                str(detection.evaluation.theoretical_profit_margin),
                [provider_id.value for provider_id in detection.selected_provider_ids],
                detection.max_quote_age.total_seconds(),
                detection.actionable,
            ]
            for detection in report.detections
        ],
        "intervals": [
            [
                interval.market_id.value,
                interval.started_at.isoformat(),
                interval.ended_at.isoformat(),
                interval.detection_count,
                str(interval.max_theoretical_profit_margin),
                interval.ever_actionable,
                interval.closed_by_end_of_stream,
            ]
            for interval in report.opportunity_intervals
        ],
        "stale_false_positives": [
            [
                stale.detected_at.isoformat(),
                stale.market_id.value,
                str(stale.counterfactual_profit_margin),
                stale.max_quote_age.total_seconds(),
            ]
            for stale in report.stale_false_positives
        ],
        "providers": [
            [
                metric.provider_id.value,
                metric.observed_quote_count,
                metric.selected_best_quote_count,
                metric.complete_book_count,
                metric.theoretical_detection_count,
                metric.actionable_detection_count,
            ]
            for metric in report.provider_metrics
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def run_benchmark(
    *,
    events: int = 10,
    markets_per_event: int = 2,
    providers: int = 2,
    update_batches: int = 3,
    updates_per_batch: int = 20,
    transports_per_provider: int = 2,
    conflicting_slots: int = 0,
    warmup_runs: int = 1,
    measured_runs: int = 3,
) -> dict[str, object]:
    """Time complete replays of one fixed, synthetic, multi-source quote corpus."""
    if warmup_runs < 0:
        raise ValueError("warmup_runs cannot be negative")
    if measured_runs < 1:
        raise ValueError("measured_runs must be positive")
    registry, corpus, initial_quotes = _corpus(
        events=events,
        markets_per_event=markets_per_event,
        providers=providers,
        update_batches=update_batches,
        updates_per_batch=updates_per_batch,
        transports_per_provider=transports_per_provider,
        conflicting_slots=conflicting_slots,
    )
    observation_count = (initial_quotes + update_batches * updates_per_batch) * (
        transports_per_provider
    )
    config = BacktestConfig(freshness_window=timedelta(seconds=max(60, update_batches + 1)))
    durations: list[int] = []
    signature: str | None = None
    summary: dict[str, int] | None = None

    for run_number in range(warmup_runs + measured_runs):
        started = perf_counter_ns()
        report = run_backtest(corpus, registry=registry, config=config)
        elapsed = perf_counter_ns() - started
        current_signature = _report_signature(report)
        if signature is not None and current_signature != signature:
            raise RuntimeError("repeated replay changed semantic report")
        signature = current_signature
        if run_number >= warmup_runs:
            durations.append(elapsed)
        if summary is None:
            summary = {
                "evaluations": report.summary.evaluation_count,
                "theoretical_detections": report.summary.theoretical_detection_count,
                "actionable_detections": report.summary.actionable_detection_count,
                "stale_false_positives": report.summary.stale_false_positive_count,
                "opportunity_intervals": report.summary.opportunity_interval_count,
            }

    assert signature is not None and summary is not None
    return {
        "workload": {
            "events": events,
            "markets_per_event": markets_per_event,
            "providers": providers,
            "initial_quotes": initial_quotes,
            "transports_per_provider": transports_per_provider,
            "update_batches": update_batches,
            "updates_per_batch": updates_per_batch,
            "conflicting_slots": conflicting_slots,
            "observations": observation_count,
            "warmup_runs": warmup_runs,
            "measured_runs": measured_runs,
        },
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "corpus_digest": corpus.digest,
        "report_signature": signature,
        "summary": summary,
        "replay_ms": _milliseconds(durations),
        "observations_per_second": round(
            observation_count * measured_runs * 1_000_000_000 / sum(durations), 1
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=_positive_int, default=10)
    parser.add_argument("--markets-per-event", type=_positive_int, default=2)
    parser.add_argument("--providers", type=_positive_int, default=2)
    parser.add_argument("--update-batches", type=_non_negative_int, default=3)
    parser.add_argument("--updates-per-batch", type=_positive_int, default=20)
    parser.add_argument("--transports-per-provider", type=_positive_int, default=2)
    parser.add_argument("--conflicting-slots", type=_non_negative_int, default=0)
    parser.add_argument("--warmup-runs", type=_non_negative_int, default=1)
    parser.add_argument("--measured-runs", type=_positive_int, default=3)
    args = parser.parse_args()
    report = run_benchmark(
        events=args.events,
        markets_per_event=args.markets_per_event,
        providers=args.providers,
        update_batches=args.update_batches,
        updates_per_batch=args.updates_per_batch,
        transports_per_provider=args.transports_per_provider,
        conflicting_slots=args.conflicting_slots,
        warmup_runs=args.warmup_runs,
        measured_runs=args.measured_runs,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
