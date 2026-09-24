"""Run deterministic multi-source detection load profiles for Phase 19."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from hashlib import sha256

from scripts.benchmark_detection import run_benchmark


@dataclass(frozen=True, slots=True)
class LoadProfile:
    """One explicit synthetic capacity profile for the production multi-source path."""

    name: str
    events: int
    markets_per_event: int
    providers: int
    updates_per_cycle: int
    transports_per_provider: int
    overlap_bps: int
    warmup_cycles: int
    measured_cycles: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("profile name must be non-empty")
        if min(
            self.events,
            self.markets_per_event,
            self.providers,
            self.updates_per_cycle,
            self.transports_per_provider,
            self.measured_cycles,
        ) < 1:
            raise ValueError("profile workload dimensions and measured_cycles must be positive")
        if self.transports_per_provider < 2:
            raise ValueError("load-matrix profiles require at least two transports")
        if self.warmup_cycles < 0:
            raise ValueError("warmup_cycles cannot be negative")
        if not 0 <= self.overlap_bps <= 10_000:
            raise ValueError("overlap_bps must be between 0 and 10000")
        if self.updates_per_cycle > self.quote_slots:
            raise ValueError("updates_per_cycle cannot exceed profile quote slots")

    @property
    def selections_per_event(self) -> int:
        """Return outcomes represented by the benchmark's market mix."""
        return 2 * self.markets_per_event + 1

    @property
    def quote_slots(self) -> int:
        """Return canonical price-provider slots before transport overlap."""
        return self.events * self.providers * self.selections_per_event

    @property
    def overlap_slots(self) -> int:
        """Return the deterministic number of slots duplicated across transports."""
        return self.quote_slots * self.overlap_bps // 10_000


REFERENCE_PROFILES = (
    LoadProfile(
        name="reference",
        events=100,
        markets_per_event=3,
        providers=3,
        updates_per_cycle=300,
        transports_per_provider=2,
        overlap_bps=2_500,
        warmup_cycles=2,
        measured_cycles=10,
    ),
    LoadProfile(
        name="scaled",
        events=250,
        markets_per_event=3,
        providers=4,
        updates_per_cycle=750,
        transports_per_provider=2,
        overlap_bps=2_500,
        warmup_cycles=2,
        measured_cycles=8,
    ),
    LoadProfile(
        name="safety_margin",
        events=400,
        markets_per_event=4,
        providers=4,
        updates_per_cycle=1_200,
        transports_per_provider=2,
        overlap_bps=3_500,
        warmup_cycles=2,
        measured_cycles=5,
    ),
)


def _semantic_signature(report: dict[str, object]) -> tuple[object, ...]:
    return (
        report["market_books"],
        report["opportunities"],
        report["result_digest"],
    )


def _profile_payload(profile: LoadProfile) -> dict[str, object]:
    return {
        "name": profile.name,
        "events": profile.events,
        "markets_per_event": profile.markets_per_event,
        "providers": profile.providers,
        "updates_per_cycle": profile.updates_per_cycle,
        "transports_per_provider": profile.transports_per_provider,
        "overlap_bps": profile.overlap_bps,
        "overlap_slots": profile.overlap_slots,
        "quote_slots": profile.quote_slots,
        "warmup_cycles": profile.warmup_cycles,
        "measured_cycles": profile.measured_cycles,
    }


def _run_profile(profile: LoadProfile) -> dict[str, object]:
    control = run_benchmark(
        events=profile.events,
        markets_per_event=profile.markets_per_event,
        providers=profile.providers,
        updates_per_cycle=profile.updates_per_cycle,
        warmup_cycles=profile.warmup_cycles,
        measured_cycles=profile.measured_cycles,
        transports_per_provider=1,
        overlap_slots=0,
    )
    multisource = run_benchmark(
        events=profile.events,
        markets_per_event=profile.markets_per_event,
        providers=profile.providers,
        updates_per_cycle=profile.updates_per_cycle,
        warmup_cycles=profile.warmup_cycles,
        measured_cycles=profile.measured_cycles,
        transports_per_provider=profile.transports_per_provider,
        overlap_slots=profile.overlap_slots,
    )

    if _semantic_signature(multisource) != _semantic_signature(control):
        raise RuntimeError(
            f"load profile {profile.name!r} changed detection semantics under transport overlap"
        )

    return {
        "profile": _profile_payload(profile),
        "semantic_parity": True,
        "result_digest": multisource["result_digest"],
        "market_books": multisource["market_books"],
        "opportunities": multisource["opportunities"],
        "equivalent_overlaps": multisource["equivalent_overlaps"],
        "conflicts": multisource["conflicts"],
        "core_updates_per_second": multisource["core_updates_per_second"],
        "stage_ms": multisource["stage_ms"],
        "workload": multisource["workload"],
        "environment": multisource["environment"],
    }


def run_load_matrix(
    *,
    profiles: tuple[LoadProfile, ...] = REFERENCE_PROFILES,
) -> dict[str, object]:
    """Run each profile and require single-source/multi-source semantic parity."""
    if not profiles:
        raise ValueError("profiles must not be empty")
    names = [profile.name for profile in profiles]
    if len(set(names)) != len(names):
        raise ValueError("profile names must be unique")

    results = tuple(_run_profile(profile) for profile in profiles)
    digest = sha256()
    for result in results:
        profile = result["profile"]
        if not isinstance(profile, dict):
            raise AssertionError("profile payload must be a dictionary")
        digest.update(
            json.dumps(profile, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        digest.update(b"|")
        digest.update(str(result["result_digest"]).encode("ascii"))
        digest.update(b"\n")

    return {
        "profile_count": len(results),
        "all_semantic_parity": True,
        "matrix_digest": digest.hexdigest(),
        "profiles": results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        action="append",
        choices=tuple(profile.name for profile in REFERENCE_PROFILES),
        help="run only the named profile; repeat to select multiple profiles",
    )
    parser.add_argument(
        "--warmup-cycles",
        type=int,
        help="override warm-up cycles for every selected profile",
    )
    parser.add_argument(
        "--measured-cycles",
        type=int,
        help="override measured cycles for every selected profile",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    selected_names = set(args.profile or ())
    profiles = tuple(
        profile
        for profile in REFERENCE_PROFILES
        if not selected_names or profile.name in selected_names
    )
    if args.warmup_cycles is not None:
        profiles = tuple(
            replace(profile, warmup_cycles=args.warmup_cycles) for profile in profiles
        )
    if args.measured_cycles is not None:
        profiles = tuple(
            replace(profile, measured_cycles=args.measured_cycles) for profile in profiles
        )
    print(json.dumps(run_load_matrix(profiles=profiles), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
