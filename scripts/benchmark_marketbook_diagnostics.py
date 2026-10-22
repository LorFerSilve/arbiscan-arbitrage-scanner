"""Measure market-book construction with many rejected quotes across markets."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from math import ceil
from statistics import median
from time import perf_counter_ns

from scripts.benchmark_detection import START, _quote, _workload

from arbiscan.domain import QuoteStatus
from arbiscan.marketbook import MarketBookBatch, MarketBookDiagnosticCode, build_market_books


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return number


def _digest(batch: MarketBookBatch) -> str:
    digest = sha256()
    for book in batch.books:
        digest.update(f"book:{book.market.id.value}\n".encode("utf-8"))
        for quote in book.quotes:
            digest.update(f"quote:{quote.id.value}\n".encode("utf-8"))
    for item in batch.diagnostics:
        market = "" if item.market_id is None else item.market_id.value
        quote = "" if item.quote_id is None else item.quote_id.value
        digest.update(
            f"diagnostic:{market}|{quote}|{item.code.value}|{item.detail}\n".encode("utf-8")
        )
    return digest.hexdigest()


def run_benchmark(
    *,
    events: int = 100,
    markets_per_event: int = 3,
    providers: int = 3,
    rejected_per_valid: int = 2,
    warmup_runs: int = 2,
    measured_runs: int = 10,
) -> dict[str, object]:
    """Time the same canonical workload repeatedly and reject semantic drift."""
    if min(events, markets_per_event, providers, measured_runs) < 1:
        raise ValueError("events, markets, providers and measured_runs must be positive")
    if min(rejected_per_valid, warmup_runs) < 0:
        raise ValueError("rejected_per_valid and warmup_runs must be non-negative")

    registry, specs = _workload(
        events=events, markets_per_event=markets_per_event, providers=providers
    )
    valid = tuple(_quote(spec, at=START, revision=0) for spec in specs)
    rejected = tuple(
        replace(_quote(spec, at=START, revision=index), status=QuoteStatus.SUSPENDED)
        for index in range(1, rejected_per_valid + 1)
        for spec in specs
    )
    quotes = (*valid, *rejected)
    expected_books = events * markets_per_event
    expected_diagnostics = len(rejected)
    elapsed: list[int] = []
    expected_digest: str | None = None

    for run in range(warmup_runs + measured_runs):
        start_ns = perf_counter_ns()
        batch = build_market_books(
            quotes,
            registry=registry,
            as_of=START,
            freshness_window=timedelta(minutes=5),
        )
        duration = perf_counter_ns() - start_ns
        if len(batch.books) != expected_books or len(batch.diagnostics) != expected_diagnostics:
            raise RuntimeError("diagnostic benchmark workload unexpectedly changed")
        if any(
            item.code is not MarketBookDiagnosticCode.INACTIVE_QUOTE for item in batch.diagnostics
        ):
            raise RuntimeError("diagnostic benchmark introduced an unexpected rejection")
        for book in batch.books:
            if book.construction_diagnostics != tuple(
                item for item in batch.diagnostics if item.market_id == book.market.id
            ):
                raise RuntimeError("per-market diagnostic attribution changed")
        current_digest = _digest(batch)
        if expected_digest is None:
            expected_digest = current_digest
        elif current_digest != expected_digest:
            raise RuntimeError("diagnostic benchmark output is nondeterministic")
        if run >= warmup_runs:
            elapsed.append(duration)

    if expected_digest is None:
        raise AssertionError("at least one measured run is required")
    ordered = sorted(elapsed)
    return {
        "workload": {
            "events": events,
            "markets_per_event": markets_per_event,
            "providers": providers,
            "valid_quotes": len(valid),
            "rejected_quotes": len(rejected),
            "rejected_per_valid": rejected_per_valid,
            "warmup_runs": warmup_runs,
            "measured_runs": measured_runs,
        },
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "market_books": expected_books,
        "diagnostics": expected_diagnostics,
        "result_digest": expected_digest,
        "market_book_ms": {
            "median": round(median(ordered) / 1_000_000, 3),
            "p95": round(ordered[ceil(len(ordered) * 0.95) - 1] / 1_000_000, 3),
            "max": round(ordered[-1] / 1_000_000, 3),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=_positive_int, default=100)
    parser.add_argument("--markets-per-event", type=_positive_int, default=3)
    parser.add_argument("--providers", type=_positive_int, default=3)
    parser.add_argument("--rejected-per-valid", type=_non_negative_int, default=2)
    parser.add_argument("--warmup-runs", type=_non_negative_int, default=2)
    parser.add_argument("--measured-runs", type=_positive_int, default=10)
    args = parser.parse_args()
    print(
        json.dumps(
            run_benchmark(
                events=args.events,
                markets_per_event=args.markets_per_event,
                providers=args.providers,
                rejected_per_valid=args.rejected_per_valid,
                warmup_runs=args.warmup_runs,
                measured_runs=args.measured_runs,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
