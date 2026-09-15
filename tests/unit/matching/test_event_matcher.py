"""Adversarial tests for deterministic cross-provider event matching."""

from datetime import UTC, datetime, timedelta

from arbiscan.domain import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventStatus,
    Participant,
    ParticipantId,
    ParticipantKind,
    ProviderEventReference,
    ProviderId,
    Sport,
)
from arbiscan.matching import (
    CanonicalEventMatchMetadata,
    CanonicalRegistry,
    EventMatchConfig,
    EventMatchReason,
    EventMatchStatus,
    EventMatcher,
    NormalizedEventEvidence,
    ParticipantOrderPolicy,
)


def _participant(slug: str, name: str, sport: Sport, kind: ParticipantKind) -> Participant:
    return Participant(
        id=ParticipantId(f"participant:{slug}"),
        sport=sport,
        name=name,
        kind=kind,
    )


def _registry(
    *,
    sport: Sport,
    kind: ParticipantKind,
    event_specs: tuple[tuple[str, datetime, tuple[Participant, ...], tuple[ProviderEventReference, ...]], ...],
) -> CanonicalRegistry:
    competition = Competition(
        id=CompetitionId(f"competition:{sport.value}:test"),
        sport=sport,
        name="Test Competition",
    )
    participants = tuple(
        {
            participant.id: participant
            for _, _, event_participants, _ in event_specs
            for participant in event_participants
        }.values()
    )
    events = tuple(
        Event(
            id=EventId(f"event:{key}"),
            sport=sport,
            competition=competition,
            participants=event_participants,
            scheduled_start=starts_at,
            status=EventStatus.SCHEDULED,
            provider_references=references,
        )
        for key, starts_at, event_participants, references in event_specs
    )
    assert all(participant.kind is kind for participant in participants)
    return CanonicalRegistry(
        competitions=(competition,),
        participants=participants,
        events=events,
        markets=(),
        selections=(),
    )


def _evidence(
    registry: CanonicalRegistry,
    *,
    participant_ids: tuple[ParticipantId, ...],
    starts_at: datetime,
    order_policy: ParticipantOrderPolicy,
    provider_id: ProviderId | None = None,
    external_event_id: str = "source:event",
    round_or_stage: str | None = None,
    venue: str | None = None,
) -> NormalizedEventEvidence:
    competition = registry.competitions[0]
    return NormalizedEventEvidence(
        provider_id=provider_id or ProviderId("provider:new"),
        external_event_id=external_event_id,
        sport=competition.sport,
        competition_id=competition.id,
        participant_ids=participant_ids,
        scheduled_start=starts_at,
        order_policy=order_policy,
        round_or_stage=round_or_stage,
        venue=venue,
    )


def test_exact_ordered_football_event_matches() -> None:
    starts_at = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
    home = _participant("arsenal", "Arsenal", Sport.FOOTBALL, ParticipantKind.TEAM)
    away = _participant("chelsea", "Chelsea", Sport.FOOTBALL, ParticipantKind.TEAM)
    registry = _registry(
        sport=Sport.FOOTBALL,
        kind=ParticipantKind.TEAM,
        event_specs=(("arsenal-chelsea", starts_at, (home, away), ()),),
    )

    decision = EventMatcher(registry).match(
        _evidence(
            registry,
            participant_ids=(home.id, away.id),
            starts_at=starts_at,
            order_policy=ParticipantOrderPolicy.ORDERED,
        )
    )

    assert decision.status is EventMatchStatus.MATCHED
    assert decision.matched_event_id == EventId("event:arsenal-chelsea")
    assert decision.confidence_bps == 9000


def test_same_teams_on_different_dates_are_rejected() -> None:
    canonical_start = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
    home = _participant("arsenal", "Arsenal", Sport.FOOTBALL, ParticipantKind.TEAM)
    away = _participant("chelsea", "Chelsea", Sport.FOOTBALL, ParticipantKind.TEAM)
    registry = _registry(
        sport=Sport.FOOTBALL,
        kind=ParticipantKind.TEAM,
        event_specs=(("fixture", canonical_start, (home, away), ()),),
    )

    decision = EventMatcher(registry).match(
        _evidence(
            registry,
            participant_ids=(home.id, away.id),
            starts_at=canonical_start + timedelta(days=7),
            order_policy=ParticipantOrderPolicy.ORDERED,
        )
    )

    assert decision.status is EventMatchStatus.REJECTED
    assert EventMatchReason.START_TIME_OUTSIDE_TOLERANCE in {
        diagnostic.reason for diagnostic in decision.diagnostics
    }


def test_swapped_order_is_rejected_when_home_away_order_is_semantic() -> None:
    starts_at = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
    home = _participant("home", "Home FC", Sport.FOOTBALL, ParticipantKind.TEAM)
    away = _participant("away", "Away FC", Sport.FOOTBALL, ParticipantKind.TEAM)
    registry = _registry(
        sport=Sport.FOOTBALL,
        kind=ParticipantKind.TEAM,
        event_specs=(("fixture", starts_at, (home, away), ()),),
    )

    decision = EventMatcher(registry).match(
        _evidence(
            registry,
            participant_ids=(away.id, home.id),
            starts_at=starts_at,
            order_policy=ParticipantOrderPolicy.ORDERED,
        )
    )

    assert decision.status is EventMatchStatus.REJECTED
    assert EventMatchReason.PARTICIPANT_ORDER_MISMATCH in {
        diagnostic.reason for diagnostic in decision.diagnostics
    }


def test_tennis_participant_order_can_be_explicitly_non_semantic() -> None:
    starts_at = datetime(2026, 9, 21, 13, 0, tzinfo=UTC)
    first = _participant("player-a", "Player A", Sport.TENNIS, ParticipantKind.PERSON)
    second = _participant("player-b", "Player B", Sport.TENNIS, ParticipantKind.PERSON)
    registry = _registry(
        sport=Sport.TENNIS,
        kind=ParticipantKind.PERSON,
        event_specs=(("tennis", starts_at, (first, second), ()),),
    )

    decision = EventMatcher(registry).match(
        _evidence(
            registry,
            participant_ids=(second.id, first.id),
            starts_at=starts_at,
            order_policy=ParticipantOrderPolicy.UNORDERED,
        )
    )

    assert decision.status is EventMatchStatus.MATCHED


def test_repeated_tennis_matchup_fails_closed_when_candidates_tie() -> None:
    first = _participant("player-a", "Player A", Sport.TENNIS, ParticipantKind.PERSON)
    second = _participant("player-b", "Player B", Sport.TENNIS, ParticipantKind.PERSON)
    source_start = datetime(2026, 9, 21, 13, 2, tzinfo=UTC)
    registry = _registry(
        sport=Sport.TENNIS,
        kind=ParticipantKind.PERSON,
        event_specs=(
            ("match-one", source_start - timedelta(minutes=2), (first, second), ()),
            ("match-two", source_start + timedelta(minutes=2), (first, second), ()),
        ),
    )

    decision = EventMatcher(registry).match(
        _evidence(
            registry,
            participant_ids=(second.id, first.id),
            starts_at=source_start,
            order_policy=ParticipantOrderPolicy.UNORDERED,
        )
    )

    assert decision.status is EventMatchStatus.AMBIGUOUS
    assert len(decision.candidates) == 2
    assert EventMatchReason.AMBIGUOUS_CANDIDATES in {
        diagnostic.reason for diagnostic in decision.diagnostics
    }


def test_low_confidence_temporal_candidate_is_rejected() -> None:
    starts_at = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
    home = _participant("home", "Home FC", Sport.FOOTBALL, ParticipantKind.TEAM)
    away = _participant("away", "Away FC", Sport.FOOTBALL, ParticipantKind.TEAM)
    registry = _registry(
        sport=Sport.FOOTBALL,
        kind=ParticipantKind.TEAM,
        event_specs=(("fixture", starts_at, (home, away), ()),),
    )

    decision = EventMatcher(registry).match(
        _evidence(
            registry,
            participant_ids=(home.id, away.id),
            starts_at=starts_at + timedelta(minutes=10),
            order_policy=ParticipantOrderPolicy.ORDERED,
        )
    )

    assert decision.status is EventMatchStatus.REJECTED
    assert decision.candidates[0].confidence_bps < 8500
    assert EventMatchReason.BELOW_CONFIDENCE_THRESHOLD in {
        diagnostic.reason for diagnostic in decision.diagnostics
    }


def test_explicit_provider_reference_allows_verified_reschedule() -> None:
    provider_id = ProviderId("provider:known")
    starts_at = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
    home = _participant("home", "Home FC", Sport.FOOTBALL, ParticipantKind.TEAM)
    away = _participant("away", "Away FC", Sport.FOOTBALL, ParticipantKind.TEAM)
    registry = _registry(
        sport=Sport.FOOTBALL,
        kind=ParticipantKind.TEAM,
        event_specs=(
            (
                "fixture",
                starts_at,
                (home, away),
                (
                    ProviderEventReference(
                        provider_id=provider_id,
                        external_event_id="known:fixture",
                    ),
                ),
            ),
        ),
    )

    decision = EventMatcher(registry).match(
        _evidence(
            registry,
            participant_ids=(home.id, away.id),
            starts_at=starts_at + timedelta(hours=3),
            order_policy=ParticipantOrderPolicy.ORDERED,
            provider_id=provider_id,
            external_event_id="known:fixture",
        )
    )

    assert decision.status is EventMatchStatus.MATCHED
    assert decision.candidates[0].explicit_provider_reference is True


def test_conflicting_provider_reference_is_hard_rejection() -> None:
    provider_id = ProviderId("provider:known")
    starts_at = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
    home = _participant("home", "Home FC", Sport.FOOTBALL, ParticipantKind.TEAM)
    away = _participant("away", "Away FC", Sport.FOOTBALL, ParticipantKind.TEAM)
    registry = _registry(
        sport=Sport.FOOTBALL,
        kind=ParticipantKind.TEAM,
        event_specs=(
            (
                "fixture",
                starts_at,
                (home, away),
                (
                    ProviderEventReference(
                        provider_id=provider_id,
                        external_event_id="known:other-fixture",
                    ),
                ),
            ),
        ),
    )

    decision = EventMatcher(registry).match(
        _evidence(
            registry,
            participant_ids=(home.id, away.id),
            starts_at=starts_at,
            order_policy=ParticipantOrderPolicy.ORDERED,
            provider_id=provider_id,
            external_event_id="known:fixture",
        )
    )

    assert decision.status is EventMatchStatus.REJECTED
    assert EventMatchReason.PROVIDER_REFERENCE_CONFLICT in {
        diagnostic.reason for diagnostic in decision.diagnostics
    }


def test_round_stage_and_venue_conflicts_fail_closed() -> None:
    starts_at = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
    home = _participant("home", "Home FC", Sport.FOOTBALL, ParticipantKind.TEAM)
    away = _participant("away", "Away FC", Sport.FOOTBALL, ParticipantKind.TEAM)
    registry = _registry(
        sport=Sport.FOOTBALL,
        kind=ParticipantKind.TEAM,
        event_specs=(("fixture", starts_at, (home, away), ()),),
    )
    matcher = EventMatcher(
        registry,
        metadata=(
            CanonicalEventMatchMetadata(
                event_id=EventId("event:fixture"),
                round_or_stage="Semi-final",
                venue="National Stadium",
            ),
        ),
    )

    decision = matcher.match(
        _evidence(
            registry,
            participant_ids=(home.id, away.id),
            starts_at=starts_at,
            order_policy=ParticipantOrderPolicy.ORDERED,
            round_or_stage="Final",
            venue="National Stadium",
        )
    )

    assert decision.status is EventMatchStatus.REJECTED
    assert EventMatchReason.STAGE_MISMATCH in {
        diagnostic.reason for diagnostic in decision.diagnostics
    }


def test_matching_configuration_is_explicit_and_validated() -> None:
    config = EventMatchConfig(
        start_time_tolerance=timedelta(minutes=15),
        referenced_start_time_tolerance=timedelta(hours=12),
        minimum_confidence_bps=9000,
        ambiguity_margin_bps=100,
    )
    assert config.minimum_confidence_bps == 9000
