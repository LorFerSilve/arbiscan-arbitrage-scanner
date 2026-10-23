"""Deterministic Phase-19 replay of transport dropout, expiry and recovery.

This is a correctness scenario using production quote state, consolidation,
market-book building, and arbitrage evaluation, not a network performance test.
"""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256

from arbiscan.arbitrage import evaluate_market
from arbiscan.domain import OddsQuote, SelectionId
from arbiscan.ingestion.multisource_state import MultiSourceLiveQuoteStore
from arbiscan.ingestion.realtime import RealtimeIngestionPolicy
from arbiscan.marketbook import build_market_books
from arbiscan.matching import CanonicalRegistry
from scripts.benchmark_detection import START, QuoteSpec, _quote, _workload

FRESHNESS = timedelta(seconds=30)


def _at(seconds: int) -> datetime:
    return START + timedelta(seconds=seconds)


def _target_quotes(
    specs: tuple[QuoteSpec, ...],
    *,
    seconds: int,
    revision: int,
    transport: int,
    target_selection: SelectionId,
    conflicting: bool = False,
) -> tuple[OddsQuote, ...]:
    return tuple(
        _quote(
            spec,
            at=_at(seconds),
            revision=revision,
            transport_number=transport,
            stable_identity=transport == 0,
            conflicting=conflicting,
        )
        for spec in specs
        if spec.selection_id == target_selection
    )


def _primary_quotes(
    specs: tuple[QuoteSpec, ...],
    *,
    seconds: int,
    revision: int,
    target_selection: SelectionId,
    include_target: bool,
) -> tuple[OddsQuote, ...]:
    return tuple(
        _quote(
            spec,
            at=_at(seconds),
            revision=revision,
            transport_number=0,
            stable_identity=True,
        )
        for spec in specs
        if include_target or spec.selection_id != target_selection
    )


def _snapshot(
    store: MultiSourceLiveQuoteStore,
    registry: CanonicalRegistry,
    *,
    scenario: str,
    phase: str,
    seconds: int,
    target_market: str,
    expected_books: int,
    expected_conflicts: int = 0,
    evicted: int = 0,
) -> dict[str, object]:
    moment = _at(seconds)
    fresh = store.fresh_quotes(as_of=moment)
    consolidation = store.last_consolidation_result
    if any(
        quote.status.value != "active"
        or quote.ingested_at > moment
        or (quote.source_timestamp or quote.ingested_at) > moment
        or moment - (quote.source_timestamp or quote.ingested_at) > FRESHNESS
        for quote in fresh
    ):
        raise AssertionError(f"{scenario}/{phase}: stale/future quote became executable")

    batch = build_market_books(
        fresh,
        registry=registry,
        as_of=moment,
        freshness_window=FRESHNESS,
    )
    market_ids = tuple(book.market.id.value for book in batch.books)
    opportunity_count = sum(
        evaluate_market(book.quotes, book.expected_selection_ids).is_arbitrage
        for book in batch.books
    )
    if len(batch.books) != expected_books or opportunity_count != expected_books:
        raise AssertionError(
            f"{scenario}/{phase}: expected {expected_books} complete books/opportunities, "
            f"got {len(batch.books)} books/{opportunity_count} opportunities"
        )
    if consolidation.conflict_count != expected_conflicts:
        raise AssertionError(
            f"{scenario}/{phase}: expected {expected_conflicts} conflicts, "
            f"got {consolidation.conflict_count}"
        )
    if (target_market in market_ids) != (expected_books == len(registry.markets)):
        raise AssertionError(f"{scenario}/{phase}: target market completeness violated")

    return {
        "phase": phase,
        "seconds": seconds,
        "stored_observations": len(store),
        "fresh_quotes": len(fresh),
        "stale_versions": store.stale_count(as_of=moment),
        "evicted_versions": evicted,
        "market_books": len(batch.books),
        "opportunities": opportunity_count,
        "market_ids": market_ids,
        "conflicts": consolidation.conflict_count,
        "equivalent_overlaps": consolidation.equivalent_overlap_count,
    }


def _expect_stale(states: list[dict[str, object]], *, expected: int, scenario: str) -> None:
    observed = states[-1]["stale_versions"]
    if observed != expected:
        raise AssertionError(f"{scenario}: expected {expected} stale versions, got {observed}")


def _run_dropout(*, redundant: bool) -> dict[str, object]:
    scenario = "redundant_feed" if redundant else "essential_feed"
    registry, specs = _workload(events=1, markets_per_event=2, providers=2)
    target = specs[0].selection_id
    market = specs[0].market_id.value
    store = MultiSourceLiveQuoteStore(RealtimeIngestionPolicy(freshness_window=FRESHNESS))

    def primary(seconds: int) -> tuple[OddsQuote, ...]:
        return _primary_quotes(
            specs,
            seconds=seconds,
            revision=seconds,
            target_selection=target,
            include_target=redundant,
        )

    def secondary(seconds: int) -> tuple[OddsQuote, ...]:
        return _target_quotes(
            specs,
            seconds=seconds,
            revision=seconds,
            transport=1,
            target_selection=target,
        )

    states: list[dict[str, object]] = []
    store.apply(primary(0) + secondary(0), observed_at=_at(0))
    states.append(
        _snapshot(
            store,
            registry,
            scenario=scenario,
            phase="healthy",
            seconds=0,
            target_market=market,
            expected_books=2,
        )
    )

    # The secondary transport stops producing updates; its old prices
    # remain eligible strictly until the freshness window expires.
    store.apply(primary(10), observed_at=_at(10))
    states.append(
        _snapshot(
            store,
            registry,
            scenario=scenario,
            phase="silent_but_fresh",
            seconds=10,
            target_market=market,
            expected_books=2,
        )
    )
    store.apply(primary(31), observed_at=_at(31))
    states.append(
        _snapshot(
            store,
            registry,
            scenario=scenario,
            phase="expired",
            seconds=31,
            target_market=market,
            expected_books=2 if redundant else 1,
        )
    )
    _expect_stale(states, expected=2, scenario=scenario)

    eviction = store.evict_stale(as_of=_at(31))
    if len(eviction.evicted) != 2:
        raise AssertionError(f"{scenario}: stale secondary observations were not evicted")
    states.append(
        _snapshot(
            store,
            registry,
            scenario=scenario,
            phase="evicted",
            seconds=31,
            target_market=market,
            expected_books=2 if redundant else 1,
            evicted=len(eviction.evicted),
        )
    )

    if not redundant:
        # A delayed packet arrives *after* eviction, but its source time
        # still points to the old, expired observation.
        old = _quote(
            specs[0],
            at=_at(0),
            revision=32,
            transport_number=1,
            stable_identity=False,
        )
        delayed = replace(old, ingested_at=_at(32))
        accepted = store.apply((delayed,), observed_at=_at(32))
        if accepted.added_count != 1:
            raise AssertionError("late packet must exercise stored-but-stale handling")
        states.append(
            _snapshot(
                store,
                registry,
                scenario=scenario,
                phase="late_stale_packet",
                seconds=32,
                target_market=market,
                expected_books=1,
            )
        )
        _expect_stale(states, expected=1, scenario=scenario)

    store.apply(primary(40) + secondary(40), observed_at=_at(40))
    states.append(
        _snapshot(
            store,
            registry,
            scenario=scenario,
            phase="recovered",
            seconds=40,
            target_market=market,
            expected_books=2,
        )
    )
    _expect_stale(states, expected=0, scenario=scenario)
    return {"name": scenario, "phases": states}


def _run_conflict() -> dict[str, object]:
    registry, specs = _workload(events=1, markets_per_event=2, providers=2)
    target = specs[0].selection_id
    market = specs[0].market_id.value
    store = MultiSourceLiveQuoteStore(RealtimeIngestionPolicy(freshness_window=FRESHNESS))

    def primary(seconds: int) -> tuple[OddsQuote, ...]:
        return _primary_quotes(
            specs,
            seconds=seconds,
            revision=seconds,
            target_selection=target,
            include_target=True,
        )

    def secondary(seconds: int, *, conflicting: bool) -> tuple[OddsQuote, ...]:
        return _target_quotes(
            specs,
            seconds=seconds,
            revision=seconds,
            transport=1,
            target_selection=target,
            conflicting=conflicting,
        )

    states: list[dict[str, object]] = []
    store.apply(primary(0) + secondary(0, conflicting=False), observed_at=_at(0))
    states.append(
        _snapshot(
            store,
            registry,
            scenario="conflict_then_recovery",
            phase="healthy",
            seconds=0,
            target_market=market,
            expected_books=2,
        )
    )
    store.apply(primary(1) + secondary(1, conflicting=True), observed_at=_at(1))
    states.append(
        _snapshot(
            store,
            registry,
            scenario="conflict_then_recovery",
            phase="equal_time_conflict",
            seconds=1,
            target_market=market,
            expected_books=1,
            expected_conflicts=2,
        )
    )
    # Later trustworthy observations supersede the conflicting equal-time
    # pair; the market can recover without bypassing conflict suppression.
    store.apply(primary(2), observed_at=_at(2))
    states.append(
        _snapshot(
            store,
            registry,
            scenario="conflict_then_recovery",
            phase="resolved",
            seconds=2,
            target_market=market,
            expected_books=2,
        )
    )
    return {"name": "conflict_then_recovery", "phases": states}


def run_feed_recovery() -> dict[str, object]:
    """Exercise production consolidation and evaluation through clock-driven outages."""
    scenarios = (
        _run_dropout(redundant=False),
        _run_dropout(redundant=True),
        _run_conflict(),
    )
    encoded = json.dumps(scenarios, sort_keys=True, separators=(",", ":"))
    return {
        "all_invariants_passed": True,
        "freshness_seconds": int(FRESHNESS.total_seconds()),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "result_digest": sha256(encoded.encode()).hexdigest(),
    }


def main() -> None:
    print(json.dumps(run_feed_recovery(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
