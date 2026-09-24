"""Benchmark fixture-backed provider polling and strict normalization."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    Participant,
    ParticipantId,
    ParticipantKind,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
)
from arbiscan.matching import CanonicalRegistry
from arbiscan.normalization import normalize_source_snapshot
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.models import (
    CanonicalIdHooks,
    OddsSnapshot,
    SourceCompetition,
    SourceEvent,
    SourceMarket,
    SourceSelectionQuote,
)
from arbiscan.providers.oddspapi import OddsPapiConfig, OddsPapiProvider
from arbiscan.providers.the_odds_api import TheOddsApiConfig, TheOddsApiProvider
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as TheOddsApiFixtureTransport

_THE_ODDS_API_NOW = datetime(2026, 9, 20, 11, 5, tzinfo=UTC)
_ODDSPAPI_NOW = datetime(2026, 9, 17, 10, 21, tzinfo=UTC)
_FRESHNESS_WINDOW = timedelta(minutes=10)


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


@dataclass(frozen=True, slots=True)
class _BenchmarkHooks(CanonicalIdHooks):
    event_external_id: str
    event_id_value: EventId
    market_ids: Mapping[str, MarketId]
    selection_ids: Mapping[tuple[str, str], SelectionId]

    def competition_id(self, record: SourceCompetition) -> CompetitionId | None:
        _ = record
        return None

    def event_id(self, record: SourceEvent) -> EventId | None:
        if record.external_id == self.event_external_id:
            return self.event_id_value
        return None

    def market_id(self, record: SourceMarket) -> MarketId | None:
        return self.market_ids.get(record.external_market_id)

    def selection_id(
        self,
        market: SourceMarket,
        record: SourceSelectionQuote,
    ) -> SelectionId | None:
        return self.selection_ids.get((market.external_market_id, record.external_selection_id))


@dataclass(frozen=True, slots=True)
class _CanonicalContext:
    hooks: _BenchmarkHooks
    registry: CanonicalRegistry


@dataclass(frozen=True, slots=True)
class _ProviderCase:
    name: str
    as_of: datetime
    build: Callable[[], tuple[ProviderAdapter, Callable[[], int]]]


def _build_the_odds_api() -> tuple[ProviderAdapter, Callable[[], int]]:
    transport = TheOddsApiFixtureTransport()
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="benchmark"),
        transport=transport,
        clock=lambda: _THE_ODDS_API_NOW,
    )
    return provider, lambda: len(transport.requests)


def _build_oddspapi() -> tuple[ProviderAdapter, Callable[[], int]]:
    transport = OddsPapiFixtureTransport()
    provider = OddsPapiProvider(
        config=OddsPapiConfig(api_key="benchmark"),
        transport=transport,
        clock=lambda: _ODDSPAPI_NOW,
    )
    return provider, lambda: len(transport.requests)


_CASES = (
    _ProviderCase(
        name="the_odds_api",
        as_of=_THE_ODDS_API_NOW,
        build=_build_the_odds_api,
    ),
    _ProviderCase(
        name="oddspapi",
        as_of=_ODDSPAPI_NOW,
        build=_build_oddspapi,
    ),
)


def _selection_role(event: SourceEvent, selection: SourceSelectionQuote) -> str:
    label = selection.label.strip().casefold()
    home = event.participants[0].name.strip().casefold()
    away = event.participants[1].name.strip().casefold()
    if label in {home, "1", "home"}:
        return "home"
    if label in {away, "2", "away"}:
        return "away"
    if label in {"draw", "x"}:
        return "draw"
    raise RuntimeError(
        f"benchmark fixture has unsupported 1X2 selection label: {selection.label!r}"
    )


def _canonical_context(event: SourceEvent, snapshot: OddsSnapshot) -> _CanonicalContext:
    if event.sport is not Sport.FOOTBALL:
        raise RuntimeError("provider benchmark currently expects the football fixtures")
    if len(event.participants) != 2:
        raise RuntimeError("provider benchmark requires exactly two event participants")

    competition = Competition(
        id=CompetitionId(f"competition:benchmark:{snapshot.provider_id.value}"),
        sport=Sport.FOOTBALL,
        name="Phase 19 provider benchmark",
    )
    home = Participant(
        id=ParticipantId(f"participant:benchmark:{snapshot.provider_id.value}:home"),
        sport=Sport.FOOTBALL,
        name=event.participants[0].name,
        kind=ParticipantKind.TEAM,
    )
    away = Participant(
        id=ParticipantId(f"participant:benchmark:{snapshot.provider_id.value}:away"),
        sport=Sport.FOOTBALL,
        name=event.participants[1].name,
        kind=ParticipantKind.TEAM,
    )
    event_id = EventId(f"event:benchmark:{snapshot.provider_id.value}")
    market_id = MarketId(f"market:benchmark:{snapshot.provider_id.value}:1x2")
    home_selection_id = SelectionId(f"selection:benchmark:{snapshot.provider_id.value}:home")
    draw_selection_id = SelectionId(f"selection:benchmark:{snapshot.provider_id.value}:draw")
    away_selection_id = SelectionId(f"selection:benchmark:{snapshot.provider_id.value}:away")

    canonical_event = Event(
        id=event_id,
        sport=Sport.FOOTBALL,
        competition=competition,
        participants=(home, away),
        scheduled_start=event.scheduled_start,
        status=EventStatus.SCHEDULED,
    )
    canonical_market = Market(
        id=market_id,
        event_id=event_id,
        kind=MarketKind.MATCH_WINNER_3_WAY,
        period=MarketPeriod.REGULATION,
    )
    canonical_selections = (
        Selection(
            id=home_selection_id,
            market_id=market_id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=home.id,
        ),
        Selection(
            id=draw_selection_id,
            market_id=market_id,
            kind=SelectionKind.DRAW,
        ),
        Selection(
            id=away_selection_id,
            market_id=market_id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=away.id,
        ),
    )

    market_ids: dict[str, MarketId] = {}
    selection_ids: dict[tuple[str, str], SelectionId] = {}
    role_ids = {
        "home": home_selection_id,
        "draw": draw_selection_id,
        "away": away_selection_id,
    }
    for market in snapshot.markets:
        if (
            market.line is not None
            or market.period_index is not None
            or market.set_index is not None
        ):
            raise RuntimeError("benchmark fixture unexpectedly contains a parameterized market")
        market_ids[market.external_market_id] = market_id
        for selection in market.selections:
            role = _selection_role(event, selection)
            selection_ids[(market.external_market_id, selection.external_selection_id)] = role_ids[
                role
            ]

    registry = CanonicalRegistry(
        competitions=(competition,),
        participants=(home, away),
        events=(canonical_event,),
        markets=(canonical_market,),
        selections=canonical_selections,
    )
    hooks = _BenchmarkHooks(
        event_external_id=event.external_id,
        event_id_value=event_id,
        market_ids=market_ids,
        selection_ids=selection_ids,
    )
    return _CanonicalContext(hooks=hooks, registry=registry)


def _semantic_digest(
    *,
    provider: ProviderAdapter,
    event: SourceEvent,
    snapshot: OddsSnapshot,
    normalized_quotes: tuple[object, ...],
) -> str:
    digest = sha256()
    digest.update(provider.provider.id.value.encode("utf-8"))
    digest.update(b"\n")
    digest.update(event.external_id.encode("utf-8"))
    digest.update(b"\n")
    for market in snapshot.markets:
        digest.update(market.external_market_id.encode("utf-8"))
        digest.update(b"|")
        digest.update(
            (market.source_timestamp.isoformat() if market.source_timestamp else "").encode("utf-8")
        )
        digest.update(b"\n")
        for selection in market.selections:
            digest.update(selection.external_selection_id.encode("utf-8"))
            digest.update(b"|")
            digest.update(selection.label.encode("utf-8"))
            digest.update(b"|")
            digest.update(selection.price.encode("utf-8"))
            digest.update(b"\n")
    for quote in normalized_quotes:
        digest.update(repr(quote).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _milliseconds(values: list[int]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median": round(median(ordered) / 1_000_000, 3),
        "p95": round(ordered[ceil(len(ordered) * 0.95) - 1] / 1_000_000, 3),
        "max": round(ordered[-1] / 1_000_000, 3),
    }


async def _run_once(case: _ProviderCase) -> dict[str, object]:
    provider, request_count = case.build()

    poll_started = perf_counter_ns()
    competitions = await provider.discover_competitions(Sport.FOOTBALL)
    if not competitions:
        raise RuntimeError(f"{case.name} fixture returned no football competition")
    events = await provider.discover_events(competitions[0].external_id)
    if not events:
        raise RuntimeError(f"{case.name} fixture returned no football event")
    event = events[0]
    snapshot = await provider.fetch_odds(event.external_id)
    poll_elapsed = perf_counter_ns() - poll_started
    if snapshot is None:
        raise RuntimeError(f"{case.name} fixture returned no odds snapshot")

    context = _canonical_context(event, snapshot)
    normalize_started = perf_counter_ns()
    result = normalize_source_snapshot(
        provider=provider.provider,
        hooks=context.hooks,
        event=event,
        snapshot=snapshot,
        registry=context.registry,
        as_of=case.as_of,
        freshness_window=_FRESHNESS_WINDOW,
    )
    normalize_elapsed = perf_counter_ns() - normalize_started
    if result.issues:
        issue_codes = ", ".join(issue.code.value for issue in result.issues)
        raise RuntimeError(f"{case.name} normalization produced issues: {issue_codes}")
    if not result.quotes:
        raise RuntimeError(f"{case.name} normalization produced no quotes")

    return {
        "poll_ns": poll_elapsed,
        "normalize_ns": normalize_elapsed,
        "requests": request_count(),
        "source_markets": len(snapshot.markets),
        "source_selections": sum(len(market.selections) for market in snapshot.markets),
        "quotes": len(result.quotes),
        "digest": _semantic_digest(
            provider=provider,
            event=event,
            snapshot=snapshot,
            normalized_quotes=tuple(result.quotes),
        ),
    }


async def _measure_case(
    case: _ProviderCase,
    *,
    warmup_runs: int,
    measured_runs: int,
) -> dict[str, object]:
    expected_digest: str | None = None
    for _ in range(warmup_runs):
        warmup = await _run_once(case)
        expected_digest = str(warmup["digest"])

    polls: list[int] = []
    normalizations: list[int] = []
    requests: int | None = None
    source_markets: int | None = None
    source_selections: int | None = None
    quotes: int | None = None

    for _ in range(measured_runs):
        result = await _run_once(case)
        digest = str(result["digest"])
        if expected_digest is None:
            expected_digest = digest
        elif digest != expected_digest:
            raise RuntimeError(f"{case.name} semantic digest changed between identical runs")

        polls.append(int(result["poll_ns"]))
        normalizations.append(int(result["normalize_ns"]))
        current_counts = (
            int(result["requests"]),
            int(result["source_markets"]),
            int(result["source_selections"]),
            int(result["quotes"]),
        )
        if requests is None:
            requests, source_markets, source_selections, quotes = current_counts
        elif current_counts != (requests, source_markets, source_selections, quotes):
            raise RuntimeError(f"{case.name} workload counts changed between identical runs")

    if expected_digest is None or requests is None:
        raise AssertionError("measured_runs validation failed")

    return {
        "adapter_requests_per_run": requests,
        "source_markets_per_run": source_markets,
        "source_selections_per_run": source_selections,
        "canonical_quotes_per_run": quotes,
        "polling_ms": _milliseconds(polls),
        "normalization_ms": _milliseconds(normalizations),
        "semantic_digest": expected_digest,
    }


async def _run_async(*, warmup_runs: int, measured_runs: int) -> dict[str, object]:
    providers: dict[str, object] = {}
    combined = sha256()
    for case in _CASES:
        report = await _measure_case(
            case,
            warmup_runs=warmup_runs,
            measured_runs=measured_runs,
        )
        providers[case.name] = report
        combined.update(case.name.encode("utf-8"))
        combined.update(b"|")
        combined.update(str(report["semantic_digest"]).encode("ascii"))
        combined.update(b"\n")

    return {
        "workload": {
            "fixture_providers": len(_CASES),
            "warmup_runs_per_provider": warmup_runs,
            "measured_runs_per_provider": measured_runs,
            "includes_network_io": False,
            "freshness_window_seconds": int(_FRESHNESS_WINDOW.total_seconds()),
        },
        "providers": providers,
        "combined_semantic_digest": combined.hexdigest(),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def run_benchmark(*, warmup_runs: int = 1, measured_runs: int = 5) -> dict[str, object]:
    """Measure fixture-backed adapter polling and production strict normalization."""
    if warmup_runs < 0:
        raise ValueError("warmup_runs must be non-negative")
    if measured_runs < 1:
        raise ValueError("measured_runs must be at least one")
    return asyncio.run(_run_async(warmup_runs=warmup_runs, measured_runs=measured_runs))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup-runs", type=_non_negative_int, default=1)
    parser.add_argument("--measured-runs", type=_positive_int, default=5)
    return parser


def main() -> None:
    args = _parser().parse_args()
    print(
        json.dumps(
            run_benchmark(
                warmup_runs=args.warmup_runs,
                measured_runs=args.measured_runs,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
