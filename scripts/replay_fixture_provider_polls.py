"""Deterministic multi-poll replay of two real-adapter football fixtures.

These are repeated *simulated* polls: each cycle loads and parses the
checked-in HTTP fixture responses through the production adapters.
Coverage loss, source timestamps, and temporary absent snapshots are
deliberate in-memory mutations, not recorded multi-poll provider traffic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256

from arbiscan.arbitrage import evaluate_market
from arbiscan.domain import OddsQuote, SelectionId
from arbiscan.ingestion import MultiSourceLiveQuoteStore, RealtimeIngestionPolicy
from arbiscan.ingestion.realtime import QuoteStoreDiagnosticCode
from arbiscan.marketbook import build_market_books
from arbiscan.matching import CanonicalRegistry, EventMatchStatus
from arbiscan.normalization import NormalizationIssueCode, normalize_source_snapshot
from arbiscan.providers.oddspapi import ODDSPAPI_PROVIDER_ID
from tests.integration import test_phase16_5_real_provider_semantics as reference
from tests.integration import test_phase16_6_real_multisource_coexistence as fixtures

FRESHNESS = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class _Phase:
    name: str
    seconds: int
    api: str
    papi: str
    expected_books: int


_PHASES = (
    _Phase("healthy", 0, "full", "full", 1),
    _Phase("partial_coverage", 10, "no_draw", "no_draw", 1),
    _Phase("essential_leg_expired", 31, "no_draw", "offline", 0),
    _Phase("late_old_revision", 32, "offline", "offline", 0),
    _Phase("provider_recovered", 40, "no_draw", "full", 1),
    _Phase("future_timestamp_rejected", 50, "future", "full", 1),
    _Phase("all_providers_expired", 81, "offline", "offline", 0),
    _Phase("both_recovered", 90, "full", "full", 1),
)


def _at(seconds: int) -> datetime:
    return reference.AS_OF + timedelta(seconds=seconds)


def _normalize_poll(
    observation: fixtures._Observation,
    registry: CanonicalRegistry,
    *,
    at: datetime,
    mode: str,
) -> tuple[tuple[OddsQuote, ...], tuple[NormalizationIssueCode, ...]]:
    hooks, decision = fixtures._hooks_for_observation(observation, registry)
    if decision.status is not EventMatchStatus.MATCHED:
        raise AssertionError("a fixture event must match the shared canonical event")

    skew = timedelta(seconds=7) if mode == "future" else timedelta(0)
    # The source-time offset prevents artificial equal-time conflict
    # between genuinely different transport fixtures with shared bookmakers.
    transport_offset = (
        timedelta(seconds=1)
        if observation.adapter.provider.id == ODDSPAPI_PROVIDER_ID
        else timedelta(0)
    )
    source_time = at + skew - transport_offset

    changed_markets = []
    for market in observation.snapshot.markets:
        selections = tuple(
            selection
            for selection in market.selections
            if mode != "no_draw"
            or reference._selection_id(observation.adapter.provider.id, selection.label)
            != reference.DRAW_SELECTION_ID
        )
        if not selections:
            continue
        changed_markets.append(replace(market, selections=selections, source_timestamp=source_time))
    snapshot = replace(
        observation.snapshot,
        markets=tuple(changed_markets),
        ingested_at=at,
    )
    normalized = normalize_source_snapshot(
        provider=observation.adapter.provider,
        hooks=hooks,
        event=observation.event,
        snapshot=snapshot,
        registry=registry,
        as_of=at,
        freshness_window=FRESHNESS,
    )
    return normalized.quotes, tuple(issue.code for issue in normalized.issues)


def _canonical_digest(quotes: tuple[OddsQuote, ...]) -> str:
    rows = sorted(
        (
            q.provider_id.value,
            (q.transport_provider_id or q.provider_id).value,
            q.event_id.value,
            q.market_id.value,
            q.selection_id.value,
            str(q.decimal_price),
            (q.source_timestamp or q.ingested_at).isoformat(),
        )
        for q in quotes
    )
    return sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def run_fixture_multi_poll_replay() -> dict[str, object]:
    """Replay fixture-backed updates using production matching, state, and evaluation."""
    registry = reference._registry()
    store = MultiSourceLiveQuoteStore(RealtimeIngestionPolicy(freshness_window=FRESHNESS))
    outcomes: list[dict[str, object]] = []
    initial_draw: OddsQuote | None = None

    for phase in _PHASES:
        moment = _at(phase.seconds)
        # Every phase genuinely reconstructs both adapters from their
        # checked-in provider-shaped JSON responses; availability is
        # simulated by withholding a parsed snapshot after that step.
        api, papi = fixtures._load_observations()
        observations = ((api, phase.api), (papi, phase.papi))
        incoming: list[OddsQuote] = []
        issues: list[str] = []

        for observation, mode in observations:
            if mode == "offline":
                continue
            normalized, rejected = _normalize_poll(observation, registry, at=moment, mode=mode)
            incoming.extend(normalized)
            issues.extend(code.value for code in rejected)
            if phase.seconds == 0 and observation.adapter.provider.id == ODDSPAPI_PROVIDER_ID:
                initial_draw = next(
                    quote
                    for quote in normalized
                    if quote.selection_id == reference.DRAW_SELECTION_ID
                    and quote.provider_id == reference.PINNACLE_ID
                )

        if phase.name == "late_old_revision":
            if initial_draw is None:
                raise AssertionError("missing initial draw quote for delayed revision")
            incoming.append(
                replace(
                    initial_draw,
                    source_timestamp=_at(-45),
                    ingested_at=moment,
                    decimal_price=Decimal("9.99"),
                )
            )

        applied = store.apply(incoming, observed_at=moment)
        fresh = store.fresh_quotes(as_of=moment)
        consolidated = store.last_consolidation_result
        books = build_market_books(
            fresh,
            registry=registry,
            as_of=moment,
            freshness_window=FRESHNESS,
            market_ids=(reference.MARKET_ID,),
        ).books
        if len(books) != phase.expected_books:
            raise AssertionError(
                f"{phase.name}: expected {phase.expected_books} complete books; got {len(books)}"
            )
        evaluated = []
        for book in books:
            if {x.selection.id for x in book.outcomes} != {
                reference.HOME_SELECTION_ID,
                reference.DRAW_SELECTION_ID,
                reference.AWAY_SELECTION_ID,
            }:
                raise AssertionError(f"{phase.name}: incomplete selection book")
            evaluated.append(evaluate_market(book.quotes, book.expected_selection_ids))

        if phase.name == "late_old_revision":
            if applied.rejected_count != 1 or {d.code for d in applied.diagnostics} != {
                QuoteStoreDiagnosticCode.OUT_OF_ORDER
            }:
                raise AssertionError("old delayed revision was not rejected")
        if phase.name == "future_timestamp_rejected":
            if tuple(issues) != (
                NormalizationIssueCode.FUTURE_SNAPSHOT.value,
                NormalizationIssueCode.FUTURE_SNAPSHOT.value,
            ):
                raise AssertionError("future timestamp must reject both API source markets")
        if phase.name == "all_providers_expired":
            if fresh:
                raise AssertionError("absent provider snapshots retained eligible quotes")

        outcomes.append(
            {
                "phase": phase.name,
                "seconds": phase.seconds,
                "provider_modes": {"the_odds_api": phase.api, "oddspapi": phase.papi},
                "normalization_issues": tuple(sorted(issues)),
                "applied_added": applied.added_count,
                "applied_updated": applied.updated_count,
                "rejected": applied.rejected_count,
                "fresh_transport_observations": len(store.fresh_observations(as_of=moment)),
                "executable_quotes": len(fresh),
                "stale_observations": store.stale_count(as_of=moment),
                "books": len(books),
                "arbitrages": sum(result.is_arbitrage for result in evaluated),
                "material_conflicts": consolidated.conflict_count,
                "quote_digest": _canonical_digest(fresh),
            }
        )
    digest = sha256(
        json.dumps(outcomes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "all_invariants_passed": True,
        "freshness_seconds": int(FRESHNESS.total_seconds()),
        "scenario": "fixture_backed_multi_poll",
        "phase_count": len(outcomes),
        "source_fixtures": ("the_odds_api", "oddspapi"),
        "includes_network_io": False,
        "phases": outcomes,
        "result_digest": digest,
    }


def main() -> None:
    print(json.dumps(run_fixture_multi_poll_replay(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
