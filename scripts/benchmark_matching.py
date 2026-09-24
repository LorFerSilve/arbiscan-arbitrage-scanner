"""Benchmark deterministic cross-provider event matching at catalog scale."""

from __future__ import annotations

import argparse
import json
import platform
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import ceil
from statistics import median
from time import perf_counter_ns

from arbiscan.domain import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventStatus,
    Participant,
    ParticipantId,
    ParticipantKind,
    ProviderId,
    Sport,
)
from arbiscan.matching import (
    CanonicalRegistry,
    EventMatchDecision,
    EventMatchStatus,
    EventMatcher,
    NormalizedEventEvidence,
    ParticipantOrderPolicy,
)

START = datetime(2026, 1, 1, 12, tzinfo=UTC)
PROVIDER_ID = ProviderId("provider:benchmark-matching")


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


def _workload(events: int) -> tuple[CanonicalRegistry, tuple[NormalizedEventEvidence, ...]]:
    competition = Competition(
        id=CompetitionId("competition:benchmark-matching"),
        sport=Sport.FOOTBALL,
        name="Benchmark League",
    )
    participants: list[Participant] = []
    canonical_events: list[Event] = []
    evidences: list[NormalizedEventEvidence] = []

    for number in range(events):
        home = Participant(
            id=ParticipantId(f"participant:benchmark:{number:05d}:home"),
            sport=Sport.FOOTBALL,
            name=f"Home {number:05d}",
            kind=ParticipantKind.TEAM,
        )
        away = Participant(
            id=ParticipantId(f"participant:benchmark:{number:05d}:away"),
            sport=Sport.FOOTBALL,
            name=f"Away {number:05d}",
            kind=ParticipantKind.TEAM,
        )
        starts_at = START + timedelta(minutes=number)
        event = Event(
            id=EventId(f"event:benchmark:{number:05d}"),
            sport=Sport.FOOTBALL,
            competition=competition,
            participants=(home, away),
            scheduled_start=starts_at,
            status=EventStatus.SCHEDULED,
        )
        participants.extend((home, away))
        canonical_events.append(event)
        evidences.append(
            NormalizedEventEvidence(
                provider_id=PROVIDER_ID,
                external_event_id=f"source:event:{number:05d}",
                sport=Sport.FOOTBALL,
                competition_id=competition.id,
                participant_ids=(home.id, away.id),
                scheduled_start=starts_at,
                order_policy=ParticipantOrderPolicy.ORDERED,
            )
        )

    registry = CanonicalRegistry(
        competitions=(competition,),
        participants=tuple(participants),
        events=tuple(canonical_events),
        markets=(),
        selections=(),
    )
    return registry, tuple(evidences)


def _decision_digest(decisions: tuple[EventMatchDecision, ...]) -> str:
    digest = sha256()
    for decision in decisions:
        digest.update(decision.status.value.encode("utf-8"))
        digest.update(b"|")
        digest.update(
            (decision.matched_event_id.value if decision.matched_event_id is not None else "").encode(
                "utf-8"
            )
        )
        digest.update(b"|")
        digest.update(str(decision.confidence_bps).encode("ascii"))
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
    matcher: EventMatcher,
    evidences: tuple[NormalizedEventEvidence, ...],
) -> tuple[int, tuple[EventMatchDecision, ...]]:
    started = perf_counter_ns()
    decisions = tuple(matcher.match(evidence) for evidence in evidences)
    elapsed = perf_counter_ns() - started
    return elapsed, decisions


def run_benchmark(
    *,
    events: int = 250,
    warmup_runs: int = 1,
    measured_runs: int = 5,
) -> dict[str, object]:
    if events < 1:
        raise ValueError("events must be at least one")
    if warmup_runs < 0:
        raise ValueError("warmup_runs must be non-negative")
    if measured_runs < 1:
        raise ValueError("measured_runs must be at least one")

    registry, evidences = _workload(events)
    matcher = EventMatcher(registry)

    for _ in range(warmup_runs):
        _, warmup = _run_once(matcher, evidences)
        if any(decision.status is not EventMatchStatus.MATCHED for decision in warmup):
            raise RuntimeError("matching benchmark warm-up produced an unexpected decision")

    durations: list[int] = []
    expected_digest: str | None = None
    for _ in range(measured_runs):
        elapsed, decisions = _run_once(matcher, evidences)
        if any(decision.status is not EventMatchStatus.MATCHED for decision in decisions):
            raise RuntimeError("matching benchmark produced an unexpected decision")
        digest = _decision_digest(decisions)
        if expected_digest is None:
            expected_digest = digest
        elif digest != expected_digest:
            raise RuntimeError("matching benchmark decisions changed between identical runs")
        durations.append(elapsed)

    if expected_digest is None:
        raise AssertionError("measured_runs validation failed")

    total_events = events * measured_runs
    return {
        "workload": {
            "canonical_events": events,
            "provider_events_per_run": events,
            "candidate_comparisons_per_run": events * events,
            "warmup_runs": warmup_runs,
            "measured_runs": measured_runs,
        },
        "matching_ms": _milliseconds(durations),
        "events_per_second": round(
            total_events * 1_000_000_000 / sum(durations),
            1,
        ),
        "decision_digest": expected_digest,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=_positive_int, default=250)
    parser.add_argument("--warmup-runs", type=_non_negative_int, default=1)
    parser.add_argument("--measured-runs", type=_positive_int, default=5)
    return parser


def main() -> None:
    args = _parser().parse_args()
    print(
        json.dumps(
            run_benchmark(
                events=args.events,
                warmup_runs=args.warmup_runs,
                measured_runs=args.measured_runs,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
