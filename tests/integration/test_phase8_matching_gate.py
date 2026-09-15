"""Phase-8 integration regressions for the quote-normalization event gate."""

import asyncio

from arbiscan.domain import EventId
from arbiscan.matching import (
    EventMatcher,
    MatchedCanonicalIdHooks,
    NormalizedEventEvidence,
    ParticipantOrderPolicy,
)
from arbiscan.normalization import NormalizationIssueCode, normalize_source_snapshot
from arbiscan.providers.synthetic import build_phase5_synthetic_scenario


def _evidence_for(event_id: EventId, source_event: object, scenario: object, provider_id: object) -> NormalizedEventEvidence:
    canonical = scenario.registry.event(event_id)  # type: ignore[attr-defined]
    assert canonical is not None
    return NormalizedEventEvidence(
        provider_id=provider_id,  # type: ignore[arg-type]
        external_event_id=source_event.external_id,  # type: ignore[attr-defined]
        sport=canonical.sport,
        competition_id=canonical.competition.id,
        participant_ids=tuple(participant.id for participant in canonical.participants),
        scheduled_start=source_event.scheduled_start,  # type: ignore[attr-defined]
        order_policy=ParticipantOrderPolicy.ORDERED,
    )


def test_only_phase8_matched_events_can_produce_canonical_quotes() -> None:
    scenario = build_phase5_synthetic_scenario()
    alpha = scenario.adapters[0]
    events = asyncio.run(alpha.discover_events("alpha:epl"))
    matched_source = next(event for event in events if event.external_id == "alpha:arb")
    unmatched_source = next(event for event in events if event.external_id == "alpha:noarb")

    decision = EventMatcher(scenario.registry).match(
        _evidence_for(
            EventId("event:phase5:arb"),
            matched_source,
            scenario,
            alpha.provider.id,
        )
    )
    base_hooks = alpha.canonical_id_hooks
    assert base_hooks is not None
    gated_hooks = MatchedCanonicalIdHooks(
        base=base_hooks,
        event_decisions={matched_source.external_id: decision},
    )

    matched_snapshot = asyncio.run(alpha.fetch_odds(matched_source.external_id))
    assert matched_snapshot is not None
    matched_result = normalize_source_snapshot(
        provider=alpha.provider,
        hooks=gated_hooks,
        event=matched_source,
        snapshot=matched_snapshot,
        registry=scenario.registry,
        as_of=scenario.as_of,
        freshness_window=scenario.freshness_window,
    )
    assert matched_result.quotes

    unmatched_snapshot = asyncio.run(alpha.fetch_odds(unmatched_source.external_id))
    assert unmatched_snapshot is not None
    unmatched_result = normalize_source_snapshot(
        provider=alpha.provider,
        hooks=gated_hooks,
        event=unmatched_source,
        snapshot=unmatched_snapshot,
        registry=scenario.registry,
        as_of=scenario.as_of,
        freshness_window=scenario.freshness_window,
    )
    assert unmatched_result.quotes == ()
    assert tuple(issue.code for issue in unmatched_result.issues) == (
        NormalizationIssueCode.UNMAPPED_EVENT,
    )
