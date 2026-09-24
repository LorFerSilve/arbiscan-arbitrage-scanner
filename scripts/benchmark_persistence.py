"""Measure SQLite audit-store quote write and replay-read throughput."""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from math import ceil
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
)
from arbiscan.domain.serialization import dumps
from arbiscan.persistence import SqliteAuditStore

START = datetime(2026, 1, 1, 12, tzinfo=UTC)


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("value must be at least one")
    return number


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return number


def _quotes(*, events: int, selections_per_event: int, providers: int) -> tuple[OddsQuote, ...]:
    quotes: list[OddsQuote] = []
    for event_number in range(events):
        event_id = EventId(f"event:persistence:{event_number:04d}")
        market_id = MarketId(f"market:persistence:{event_number:04d}")
        at = START + timedelta(seconds=event_number)
        for selection_number in range(selections_per_event):
            selection_id = SelectionId(
                f"selection:persistence:{event_number:04d}:{selection_number:02d}"
            )
            for provider_number in range(providers):
                provider_id = ProviderId(f"provider:persistence:{provider_number:02d}")
                quotes.append(
                    OddsQuote(
                        id=QuoteId(
                            f"quote:persistence:{event_number:04d}:"
                            f"{selection_number:02d}:{provider_number:02d}"
                        ),
                        provider_id=provider_id,
                        event_id=event_id,
                        market_id=market_id,
                        selection_id=selection_id,
                        decimal_price=Decimal("2.10") + Decimal(provider_number) / Decimal(100),
                        source_event_id=event_id.value,
                        source_market_id=market_id.value,
                        source_selection_id=selection_id.value,
                        source_timestamp=at,
                        ingested_at=at,
                        status=QuoteStatus.ACTIVE,
                        trace_id=f"trace:persistence:{event_number:04d}:"
                        f"{selection_number:02d}:{provider_number:02d}",
                    )
                )
    return tuple(sorted(quotes, key=lambda quote: (quote.ingested_at, quote.id.value)))


def _digest(quotes: tuple[OddsQuote, ...]) -> str:
    digest = sha256()
    for quote in quotes:
        digest.update(dumps(quote).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _milliseconds(values: list[int]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median": round(median(ordered) / 1_000_000, 3),
        "p95": round(ordered[ceil(len(ordered) * 0.95) - 1] / 1_000_000, 3),
        "max": round(ordered[-1] / 1_000_000, 3),
    }


def _run_once(
    database: Path,
    quotes: tuple[OddsQuote, ...],
    *,
    start_at: datetime,
    end_at: datetime,
    expected_filtered: tuple[OddsQuote, ...],
) -> dict[str, int]:
    store = SqliteAuditStore(database)
    store.migrate()

    started = perf_counter_ns()
    for quote in quotes:
        store.persist_quote(quote)
    written = perf_counter_ns()
    loaded = store.load_quotes()
    read_all = perf_counter_ns()
    filtered = store.load_quotes(
        start_at=start_at,
        end_at=end_at,
        provider_ids=(ProviderId("provider:persistence:00"),),
    )
    read_filtered = perf_counter_ns()

    if loaded != quotes or filtered != expected_filtered:
        raise RuntimeError("persistence replay diverged from the fixed quote corpus")
    with closing(sqlite3.connect(database)) as connection:
        audit_count = connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    if audit_count != len(quotes):
        raise RuntimeError("persistence audit-event count diverged from the quote corpus")

    return {
        "write": written - started,
        "read_all": read_all - written,
        "read_filtered": read_filtered - read_all,
    }


def run_benchmark(
    *,
    events: int,
    selections_per_event: int,
    providers: int,
    warmup_runs: int,
    measured_runs: int,
) -> dict[str, object]:
    """Time fresh-database inserts and reads, rejecting divergent results."""
    if min(events, selections_per_event, providers, measured_runs) < 1:
        raise ValueError("workload dimensions and measured_runs must be positive")
    if warmup_runs < 0:
        raise ValueError("warmup_runs cannot be negative")

    quotes = _quotes(events=events, selections_per_event=selections_per_event, providers=providers)
    start_at = START + timedelta(seconds=events // 4)
    end_at = START + timedelta(seconds=(events * 3) // 4)
    expected_filtered = tuple(
        quote
        for quote in quotes
        if start_at <= quote.ingested_at <= end_at
        and quote.provider_id == ProviderId("provider:persistence:00")
    )
    durations: dict[str, list[int]] = {name: [] for name in ("write", "read_all", "read_filtered")}
    with TemporaryDirectory(prefix="arbiscan-persistence-") as directory:
        for run_number in range(warmup_runs + measured_runs):
            sample = _run_once(
                Path(directory) / f"run-{run_number}.sqlite3",
                quotes,
                start_at=start_at,
                end_at=end_at,
                expected_filtered=expected_filtered,
            )
            if run_number >= warmup_runs:
                for name, duration in sample.items():
                    durations[name].append(duration)

    return {
        "workload": {
            "events": events,
            "selections_per_event": selections_per_event,
            "providers": providers,
            "quotes": len(quotes),
            "filtered_quotes": len(expected_filtered),
            "warmup_runs": warmup_runs,
            "measured_runs": measured_runs,
        },
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "corpus_sha256": _digest(quotes),
        "filtered_sha256": _digest(expected_filtered),
        "write_quotes_per_second": round(
            len(quotes) * measured_runs * 1_000_000_000 / sum(durations["write"]), 1
        ),
        "read_quotes_per_second": round(
            len(quotes) * measured_runs * 1_000_000_000 / sum(durations["read_all"]), 1
        ),
        "stage_ms": {name: _milliseconds(values) for name, values in durations.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=_positive_int, default=20)
    parser.add_argument("--selections-per-event", type=_positive_int, default=7)
    parser.add_argument("--providers", type=_positive_int, default=3)
    parser.add_argument("--warmup-runs", type=_non_negative_int, default=1)
    parser.add_argument("--measured-runs", type=_positive_int, default=3)
    args = parser.parse_args()
    report = run_benchmark(
        events=args.events,
        selections_per_event=args.selections_per_event,
        providers=args.providers,
        warmup_runs=args.warmup_runs,
        measured_runs=args.measured_runs,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
