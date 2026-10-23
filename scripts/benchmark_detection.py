"""Measure the deterministic post-ingestion detection path without provider I/O."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import Counter
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
    stable_identity: bool = False,
) -> OddsQuote:
    transport_suffix = (
        ""
        if stable_identity or transport_number is None or transport_number == 0
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
    nonoverlap_transport_number: int = 0,
) -> tuple[OddsQuote, ...]:
    if transports_per_provider == 1:
        return (_quote(spec, at=at, revision=revision),)
    if not overlapping:
        if not 0 <= nonoverlap_transport_number < transports_per_provider:
            raise ValueError("nonoverlap transport index out of range")
        return (
            _quote(
                spec,
                at=at,
                revision=revision,
                transport_number=nonoverlap_transport_number,
                stable_identity=True,
            ),
        )
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


def _missing_quote_indices(
    specs: tuple[QuoteSpec, ...],
    *,
    missing_slots: int,
    missing_pattern: str,
    missing_seed: int,
) -> frozenset[int]:
    """Build a reproducible source-coverage mask, shared by all transports."""
    if missing_pattern not in ("tail", "dispersed", "selection"):
        raise ValueError("missing_pattern must be 'tail', 'dispersed', or 'selection'")
    if missing_seed < 0:
        raise ValueError("missing_seed must be non-negative")
    if missing_slots < 0 or missing_slots >= len(specs):
        raise ValueError("missing_slots must be between zero and initial quote count - 1")
    if missing_pattern == "tail":
        return frozenset(range(len(specs) - missing_slots, len(specs)))

    def rank(key: str) -> bytes:
        return sha256(f"{missing_seed}:{key}".encode()).digest()

    if missing_pattern == "dispersed":
        ordered = sorted(range(len(specs)), key=lambda i: (rank(str(i)), i))
        return frozenset(ordered[:missing_slots])

    provider_count = len({spec.provider_id for spec in specs})
    if missing_slots % provider_count:
        raise ValueError("selection missing pattern requires a multiple of provider count")
    selection_keys = tuple(
        sorted({spec.selection_id for spec in specs}, key=lambda item: item.value)
    )
    ordered_selections = sorted(selection_keys, key=lambda item: (rank(item.value), item.value))
    masked_selections = set(ordered_selections[: missing_slots // provider_count])
    return frozenset(
        index for index, spec in enumerate(specs) if spec.selection_id in masked_selections
    )


def _coverage_summary(
    registry: CanonicalRegistry,
    specs: tuple[QuoteSpec, ...],
    missing_indices: frozenset[int],
    *,
    provider_count: int,
) -> dict[str, object]:
    """Count absent selections separately from partially covered selections."""
    available = tuple(spec for index, spec in enumerate(specs) if index not in missing_indices)
    per_selection = Counter(spec.selection_id for spec in available)
    missing_selections = {item.id for item in registry.selections if per_selection[item.id] == 0}
    incomplete_market_ids = {
        item.market_id for item in registry.selections if item.id in missing_selections
    }
    affected_events = {specs[index].event_id for index in missing_indices}
    mask_digest = sha256()
    for index in sorted(missing_indices):
        spec = specs[index]
        mask_digest.update(f"{spec.provider_id.value}|{spec.selection_id.value}\n".encode())
    return {
        "complete_markets_per_cycle": len(registry.markets) - len(incomplete_market_ids),
        "incomplete_markets_per_cycle": len(incomplete_market_ids),
        "fully_missing_selection_legs": len(missing_selections),
        "partially_covered_selection_legs": sum(
            0 < count < provider_count for count in per_selection.values()
        ),
        "events_with_missing_slots": len(affected_events),
        "providers_with_missing_slots": len(
            {specs[index].provider_id for index in missing_indices}
        ),
        "missing_mask_digest": mask_digest.hexdigest(),
    }


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
    coverage_mode: str = "primary",
    missing_slots: int = 0,
    missing_pattern: str = "tail",
    missing_seed: int = 0,
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
    if conflicting_slots and transports_per_provider < 2:
        raise ValueError("conflicting_slots requires at least two transports per provider")
    if conflicting_slots < 0 or conflicting_slots > resolved_overlap_slots:
        raise ValueError("conflicting_slots must be between zero and overlap_slots")
    if coverage_mode not in ("primary", "distributed"):
        raise ValueError("coverage_mode must be 'primary' or 'distributed'")
    missing_indices = _missing_quote_indices(
        specs,
        missing_slots=missing_slots,
        missing_pattern=missing_pattern,
        missing_seed=missing_seed,
    )
    active_slots = len(specs) - len(missing_indices)
    active_overlapping_indices = tuple(
        index for index in range(resolved_overlap_slots) if index not in missing_indices
    )
    if conflicting_slots > len(active_overlapping_indices):
        raise ValueError(
            "conflicting_slots cannot exceed unmasked overlapping quote slots"
        )
    conflicting_indices = frozenset(active_overlapping_indices[:conflicting_slots])
    active_overlap_slots = len(active_overlapping_indices)
    unique_slots_by_transport = [0] * transports_per_provider
    for index in range(resolved_overlap_slots, len(specs)):
        if index in missing_indices:
            continue
        transport = index % transports_per_provider if coverage_mode == "distributed" else 0
        unique_slots_by_transport[transport] += 1
    coverage_summary = _coverage_summary(registry, specs, missing_indices, provider_count=providers)

    window = timedelta(seconds=max(300, warmup_cycles + measured_cycles + 1))
    policy = RealtimeIngestionPolicy(freshness_window=window)
    store: LiveQuoteStore = (
        MultiSourceLiveQuoteStore(policy) if transports_per_provider > 1 else LiveQuoteStore(policy)
    )
    initial = (
        quote
        for spec_index, spec in enumerate(specs)
        if spec_index not in missing_indices
        for quote in _observations(
            spec,
            at=START,
            revision=0,
            transports_per_provider=transports_per_provider,
            conflicting=spec_index in conflicting_indices,
            overlapping=spec_index < resolved_overlap_slots,
            nonoverlap_transport_number=(
                spec_index % transports_per_provider if coverage_mode == "distributed" else 0
            ),
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
            if spec_index % len(specs) not in missing_indices
            for quote in _observations(
                specs[spec_index % len(specs)],
                at=at,
                revision=cycle,
                transports_per_provider=transports_per_provider,
                conflicting=spec_index % len(specs) in conflicting_indices,
                overlapping=spec_index % len(specs) < resolved_overlap_slots,
                nonoverlap_transport_number=(
                    spec_index % len(specs) % transports_per_provider
                    if coverage_mode == "distributed"
                    else 0
                ),
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
        complete_markets = coverage_summary["complete_markets_per_cycle"]
        if not isinstance(complete_markets, int):
            raise AssertionError("coverage summary must report complete markets")
        if len(books) > complete_markets or (
            conflicting_slots == 0 and len(books) != complete_markets
        ):
            raise RuntimeError("incomplete synthetic market produced an executable book")

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
            "active_quote_slots": active_slots,
            "missing_slots": missing_slots,
            "missing_pattern": missing_pattern,
            "missing_seed": missing_seed,
            **coverage_summary,
            "coverage_mode": coverage_mode,
            "unique_slots_by_transport": tuple(unique_slots_by_transport),
            "transports_per_provider": transports_per_provider,
            "overlap_slots": resolved_overlap_slots,
            "overlap_fraction": round(resolved_overlap_slots / len(specs), 4),
            "initial_observations": active_slots
            + active_overlap_slots * (transports_per_provider - 1),
            "updates_per_cycle": updates_per_cycle,
            "measured_update_observations": measured_update_observations,
            "update_observations_per_cycle": round(
                measured_update_observations / measured_cycles,
                2,
            ),
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
    parser.add_argument("--coverage-mode", choices=("primary", "distributed"), default="primary")
    parser.add_argument("--missing-slots", type=_non_negative_int, default=0)
    parser.add_argument(
        "--missing-pattern", choices=("tail", "dispersed", "selection"), default="tail"
    )
    parser.add_argument("--missing-seed", type=_non_negative_int, default=0)
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
        coverage_mode=args.coverage_mode,
        missing_slots=args.missing_slots,
        missing_pattern=args.missing_pattern,
        missing_seed=args.missing_seed,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
