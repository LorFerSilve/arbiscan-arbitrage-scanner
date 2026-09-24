"""Measure the deterministic post-ingestion detection path without provider I/O."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from math import ceil
from statistics import median
from time import perf_counter_ns

from arbiscan.arbitrage import build_opportunity, evaluate_market
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
    OpportunityId,
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
from arbiscan.ingestion.multisource_state import MultiSourceLiveQuoteStore
from arbiscan.ingestion.realtime import LiveQuoteStore, RealtimeIngestionPolicy
from arbiscan.marketbook import build_market_books
from arbiscan.matching import CanonicalRegistry

START = datetime(2026, 1, 1, 12, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class QuoteSpec:
    provider_id: ProviderId
    event_id: EventId
    market_id: MarketId
    selection_id: SelectionId
    price: Decimal


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


def _workload(
    *, events: int, markets_per_event: int, providers: int
) -> tuple[CanonicalRegistry, tuple[QuoteSpec, ...]]:
    competition = Competition(
        id=CompetitionId("competition:benchmark"), sport=Sport.FOOTBALL, name="Benchmark League"
    )
    participants: list[Participant] = []
    event_values: list[Event] = []
    markets: list[Market] = []
    selections: list[Selection] = []
    specs: list[QuoteSpec] = []

    for event_number in range(events):
        event_id = EventId(f"event:benchmark:{event_number}")
        home = Participant(
            id=ParticipantId(f"participant:benchmark:{event_number}:home"),
            sport=Sport.FOOTBALL,
            name=f"Home {event_number}",
            kind=ParticipantKind.TEAM,
        )
        away = Participant(
            id=ParticipantId(f"participant:benchmark:{event_number}:away"),
            sport=Sport.FOOTBALL,
            name=f"Away {event_number}",
            kind=ParticipantKind.TEAM,
        )
        participants.extend((home, away))
        event_values.append(
            Event(
                id=event_id,
                sport=Sport.FOOTBALL,
                competition=competition,
                participants=(home, away),
                scheduled_start=START + timedelta(days=1),
                status=EventStatus.SCHEDULED,
            )
        )

        for market_number in range(markets_per_event):
            market_id = MarketId(f"market:benchmark:{event_number}:{market_number}")
            market_selections: tuple[Selection, ...]
            if market_number == 0:
                market = Market(
                    id=market_id,
                    event_id=event_id,
                    kind=MarketKind.MATCH_WINNER_3_WAY,
                    period=MarketPeriod.REGULATION,
                )
                market_selections = (
                    Selection(
                        id=SelectionId(f"selection:benchmark:{event_number}:winner:home"),
                        market_id=market_id,
                        kind=SelectionKind.PARTICIPANT,
                        participant_id=home.id,
                    ),
                    Selection(
                        id=SelectionId(f"selection:benchmark:{event_number}:winner:draw"),
                        market_id=market_id,
                        kind=SelectionKind.DRAW,
                    ),
                    Selection(
                        id=SelectionId(f"selection:benchmark:{event_number}:winner:away"),
                        market_id=market_id,
                        kind=SelectionKind.PARTICIPANT,
                        participant_id=away.id,
                    ),
                )
                price = Decimal("3.20")
            else:
                market = Market(
                    id=market_id,
                    event_id=event_id,
                    kind=MarketKind.TOTAL_POINTS,
                    period=MarketPeriod.REGULATION,
                    line=Decimal(market_number) + Decimal("0.5"),
                )
                market_selections = (
                    Selection(
                        id=SelectionId(f"selection:benchmark:{event_number}:{market_number}:over"),
                        market_id=market_id,
                        kind=SelectionKind.OVER,
                    ),
                    Selection(
                        id=SelectionId(f"selection:benchmark:{event_number}:{market_number}:under"),
                        market_id=market_id,
                        kind=SelectionKind.UNDER,
                    ),
                )
                price = Decimal("2.10")
            markets.append(market)
            selections.extend(market_selections)
            for provider_number in range(providers):
                provider_id = ProviderId(f"provider:benchmark:{provider_number}")
                for selection in market_selections:
                    specs.append(
                        QuoteSpec(
                            provider_id=provider_id,
                            event_id=event_id,
                            market_id=market_id,
                            selection_id=selection.id,
                            price=price + Decimal(provider_number) / Decimal("100"),
                        )
                    )

    registry = CanonicalRegistry(
        competitions=(competition,),
        participants=tuple(participants),
        events=tuple(event_values),
        markets=tuple(markets),
        selections=tuple(selections),
    )
    return registry, tuple(specs)


def _quote(
    spec: QuoteSpec,
    *,
    at: datetime,
    revision: int,
    transport_number: int | None = None,
    conflicting: bool = False,
) -> OddsQuote:
    transport_suffix = (
        ""
        if transport_number is None or transport_number == 0
        else f":transport:{transport_number}"
    )
    return OddsQuote(
        id=QuoteId(
            f"quote:benchmark:{spec.provider_id.value}:{spec.selection_id.value}"
            f"{transport_suffix}:{revision}"
        ),
        provider_id=spec.provider_id,
        transport_provider_id=(
            None
            if transport_number is None
            else ProviderId(f"transport:benchmark:{transport_number}")
        ),
        event_id=spec.event_id,
        market_id=spec.market_id,
        selection_id=spec.selection_id,
        decimal_price=spec.price + Decimal("0.01") if conflicting else spec.price,
        source_event_id=spec.event_id.value,
        source_market_id=spec.market_id.value,
        source_selection_id=spec.selection_id.value,
        source_timestamp=at,
        ingested_at=at,
        status=QuoteStatus.ACTIVE,
        trace_id=(
            f"trace:benchmark:{spec.provider_id.value}:{spec.selection_id.value}"
            f"{transport_suffix}:{revision}"
        ),
    )


def _observations(
    spec: QuoteSpec,
    *,
    at: datetime,
    revision: int,
    transports_per_provider: int,
    conflicting: bool,
    overlapping: bool = True,
) -> tuple[OddsQuote, ...]:
    if transports_per_provider == 1:
        return (_quote(spec, at=at, revision=revision),)
    if not overlapping:
        return (_quote(spec, at=at, revision=revision, transport_number=0),)
    return tuple(
        _quote(
            spec,
            at=at,
            revision=revision,
            transport_number=transport_number,
            conflicting=conflicting and transport_number == transports_per_provider - 1,
        )
        for transport_number in range(transports_per_provider)
    )


def _milliseconds(values: list[int]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median": round(median(ordered) / 1_000_000, 3),
        "p95": round(ordered[ceil(len(ordered) * 0.95) - 1] / 1_000_000, 3),
        "max": round(ordered[-1] / 1_000_000, 3),
    }


def run_benchmark(
    *,
    events: int,
    markets_per_event: int,
    providers: int,
    updates_per_cycle: int,
    warmup_cycles: int,
    measured_cycles: int,
    transports_per_provider: int = 1,
    overlap_slots: int | None = None,
    conflicting_slots: int = 0,
) -> dict[str, object]:
    """Return stage timings and a stable semantic digest for a fixed synthetic load."""
    if (
        min(
            events,
            markets_per_event,
            providers,
            updates_per_cycle,
            measured_cycles,
            transports_per_provider,
        )
        < 1
    ):
        raise ValueError("workload dimensions and measured_cycles must be positive")
    if warmup_cycles < 0:
        raise ValueError("warmup_cycles cannot be negative")
    registry, specs = _workload(
        events=events, markets_per_event=markets_per_event, providers=providers
    )
    if updates_per_cycle > len(specs):
        raise ValueError("updates_per_cycle cannot exceed initial quote count")
    resolved_overlap_slots = (
        len(specs) if overlap_slots is None and transports_per_provider > 1 else overlap_slots or 0
    )
    if resolved_overlap_slots < 0 or resolved_overlap_slots > len(specs):
        raise ValueError("overlap_slots must be between zero and initial quote count")
    if resolved_overlap_slots and transports_per_provider < 2:
        raise ValueError("overlap_slots requires at least two transports per provider")
    if conflicting_slots < 0 or conflicting_slots > resolved_overlap_slots:
        raise ValueError("conflicting_slots must be between zero and overlap_slots")
    if conflicting_slots and transports_per_provider < 2:
        raise ValueError("conflicting_slots requires at least two transports per provider")

    window = timedelta(seconds=max(300, warmup_cycles + measured_cycles + 1))
    policy = RealtimeIngestionPolicy(freshness_window=window)
    store: LiveQuoteStore = (
        MultiSourceLiveQuoteStore(policy) if transports_per_provider > 1 else LiveQuoteStore(policy)
    )
    initial = (
        quote
        for spec_index, spec in enumerate(specs)
        for quote in _observations(
            spec,
            at=START,
            revision=0,
            transports_per_provider=transports_per_provider,
            conflicting=spec_index < conflicting_slots,
            overlapping=spec_index < resolved_overlap_slots,
        )
    )
    store.apply(initial, observed_at=START)
    fresh_stage = "fresh_consolidate" if transports_per_provider > 1 else "fresh"
    durations: dict[str, list[int]] = {
        name: [] for name in ("apply", fresh_stage, "book", "evaluate", "cycle")
    }
    digest = sha256()
    opportunity_count = 0
    book_count = 0
    executable_quote_count = 0
    equivalent_overlap_count = 0
    conflict_count = 0
    measured_update_observations = 0

    for cycle in range(1, warmup_cycles + measured_cycles + 1):
        at = START + timedelta(seconds=cycle)
        offset = (cycle * updates_per_cycle) % len(specs)
        updates = tuple(
            quote
            for spec_index in range(offset, offset + updates_per_cycle)
            for quote in _observations(
                specs[spec_index % len(specs)],
                at=at,
                revision=cycle,
                transports_per_provider=transports_per_provider,
                conflicting=spec_index % len(specs) < conflicting_slots,
                overlapping=spec_index % len(specs) < resolved_overlap_slots,
            )
        )
        started = perf_counter_ns()
        store.apply(updates, observed_at=at)
        applied = perf_counter_ns()
        fresh = store.fresh_quotes(as_of=at)
        consolidation = (
            store.last_consolidation_result
            if isinstance(store, MultiSourceLiveQuoteStore)
            else None
        )
        fetched = perf_counter_ns()
        books = build_market_books(
            fresh,
            registry=registry,
            as_of=at,
            freshness_window=window,
        ).books
        built = perf_counter_ns()

        cycle_signatures: list[str] = []
        cycle_opportunities = 0
        for book in books:
            evaluation = evaluate_market(book.quotes, book.expected_selection_ids)
            if evaluation.is_arbitrage:
                opportunity = build_opportunity(
                    evaluation,
                    opportunity_id=OpportunityId(
                        f"opportunity:benchmark:{book.market.id.value}:{cycle}"
                    ),
                    detected_at=at,
                )
                cycle_opportunities += 1
                cycle_signatures.append(
                    f"{book.market.id.value}:{','.join(value.value for value in opportunity.quote_ids)}"
                )
        evaluated = perf_counter_ns()

        if cycle > warmup_cycles:
            for name, duration in (
                ("apply", applied - started),
                (fresh_stage, fetched - applied),
                ("book", built - fetched),
                ("evaluate", evaluated - built),
                ("cycle", evaluated - started),
            ):
                durations[name].append(duration)
            book_count += len(books)
            opportunity_count += cycle_opportunities
            executable_quote_count += len(fresh)
            measured_update_observations += len(updates)
            if consolidation is not None:
                equivalent_overlap_count += consolidation.equivalent_overlap_count
                conflict_count += consolidation.conflict_count
            digest.update("\n".join(cycle_signatures).encode("utf-8"))
            digest.update(b"\n")

    return {
        "workload": {
            "events": events,
            "markets_per_event": markets_per_event,
            "providers": providers,
            "initial_quotes": len(specs),
            "transports_per_provider": transports_per_provider,
            "overlap_slots": resolved_overlap_slots,
            "overlap_fraction": round(resolved_overlap_slots / len(specs), 4),
            "initial_observations": len(specs)
            + resolved_overlap_slots * (transports_per_provider - 1),
            "updates_per_cycle": updates_per_cycle,
            "measured_update_observations": measured_update_observations,
            "mean_update_observations_per_cycle": round(
                measured_update_observations / measured_cycles,
                2,
            ),
            "conflicting_slots": conflicting_slots,
            "warmup_cycles": warmup_cycles,
            "measured_cycles": measured_cycles,
        },
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "executable_quotes": executable_quote_count,
        "equivalent_overlaps": equivalent_overlap_count,
        "conflicts": conflict_count,
        "market_books": book_count,
        "opportunities": opportunity_count,
        "result_digest": digest.hexdigest(),
        "core_updates_per_second": round(
            measured_update_observations * 1_000_000_000 / sum(durations["apply"]),
            1,
        ),
        "stage_ms": {name: _milliseconds(values) for name, values in durations.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=_positive_int, default=100)
    parser.add_argument("--markets-per-event", type=_positive_int, default=3)
    parser.add_argument("--providers", type=_positive_int, default=3)
    parser.add_argument("--updates-per-cycle", type=_positive_int, default=300)
    parser.add_argument("--warmup-cycles", type=_non_negative_int, default=3)
    parser.add_argument("--measured-cycles", type=_positive_int, default=20)
    parser.add_argument("--transports-per-provider", type=_positive_int, default=1)
    parser.add_argument("--overlap-slots", type=_non_negative_int)
    parser.add_argument("--conflicting-slots", type=_non_negative_int, default=0)
    args = parser.parse_args()
    report = run_benchmark(
        events=args.events,
        markets_per_event=args.markets_per_event,
        providers=args.providers,
        updates_per_cycle=args.updates_per_cycle,
        warmup_cycles=args.warmup_cycles,
        measured_cycles=args.measured_cycles,
        transports_per_provider=args.transports_per_provider,
        overlap_slots=args.overlap_slots,
        conflicting_slots=args.conflicting_slots,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
