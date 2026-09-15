"""Tests for Phase-7-to-Phase-8 event evidence preparation."""

from datetime import UTC, datetime

from arbiscan.domain import (
    CompetitionId,
    ParticipantId,
    ParticipantKind,
    ProviderId,
    Sport,
)
from arbiscan.matching import EventMatchReason, ParticipantOrderPolicy
from arbiscan.normalization import (
    CompetitionAlias,
    CompetitionNormalizer,
    ParticipantAlias,
    ParticipantNormalizer,
    prepare_event_evidence,
)
from arbiscan.providers.models import SourceCompetition, SourceEvent, SourceParticipant


def _competition_normalizer() -> CompetitionNormalizer:
    return CompetitionNormalizer(
        (
            CompetitionAlias(
                "Premier League",
                CompetitionId("competition:england:premier-league"),
                Sport.FOOTBALL,
                region="England",
                season="2026/27",
            ),
            CompetitionAlias(
                "Premier League",
                CompetitionId("competition:bangladesh:premier-league"),
                Sport.FOOTBALL,
                region="Bangladesh",
                season="2026",
            ),
        )
    )


def test_localized_and_abbreviated_participants_prepare_canonical_evidence() -> None:
    provider_id = ProviderId("provider:test")
    competition_id = CompetitionId("competition:england:premier-league")
    arsenal = ParticipantId("participant:arsenal")
    manchester = ParticipantId("participant:manchester-united")
    participant_normalizer = ParticipantNormalizer(
        (
            ParticipantAlias(
                "Arsenal FC",
                arsenal,
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=competition_id,
            ),
            ParticipantAlias(
                "Man United",
                manchester,
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=competition_id,
            ),
        )
    )
    competition = SourceCompetition(
        external_id="epl",
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
        season="2026/27",
    )
    event = SourceEvent(
        external_id="provider:arsenal-mun",
        sport=Sport.FOOTBALL,
        competition_external_id="epl",
        participants=(
            SourceParticipant("arsenal", "Arsenal FC", role="home"),
            SourceParticipant("mun", "Man United", role="away"),
        ),
        scheduled_start=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
    )

    result = prepare_event_evidence(
        provider_id=provider_id,
        event=event,
        competition=competition,
        competition_normalizer=_competition_normalizer(),
        participant_normalizer=participant_normalizer,
        participant_kind=ParticipantKind.TEAM,
        order_policy=ParticipantOrderPolicy.ORDERED,
    )

    assert result.diagnostics == ()
    assert result.evidence is not None
    assert result.evidence.competition_id == competition_id
    assert result.evidence.participant_ids == (arsenal, manchester)


def test_same_named_competition_without_context_fails_closed() -> None:
    competition = SourceCompetition(
        external_id="premier",
        sport=Sport.FOOTBALL,
        name="Premier League",
    )
    event = SourceEvent(
        external_id="event",
        sport=Sport.FOOTBALL,
        competition_external_id="premier",
        participants=(SourceParticipant("team", "Team"),),
        scheduled_start=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
    )

    result = prepare_event_evidence(
        provider_id=ProviderId("provider:test"),
        event=event,
        competition=competition,
        competition_normalizer=_competition_normalizer(),
        participant_normalizer=ParticipantNormalizer(()),
        participant_kind=ParticipantKind.TEAM,
        order_policy=ParticipantOrderPolicy.ORDERED,
    )

    assert result.evidence is None
    assert result.diagnostics[0].reason is EventMatchReason.AMBIGUOUS_COMPETITION


def test_women_or_reserve_lookalike_is_not_silently_collapsed() -> None:
    competition_id = CompetitionId("competition:england:premier-league")
    participant_normalizer = ParticipantNormalizer(
        (
            ParticipantAlias(
                "Manchester United",
                ParticipantId("participant:manchester-united"),
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=competition_id,
            ),
        )
    )
    competition = SourceCompetition(
        external_id="epl",
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
        season="2026/27",
    )
    event = SourceEvent(
        external_id="women-event",
        sport=Sport.FOOTBALL,
        competition_external_id="epl",
        participants=(SourceParticipant("women", "Manchester United Women"),),
        scheduled_start=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
    )

    result = prepare_event_evidence(
        provider_id=ProviderId("provider:test"),
        event=event,
        competition=competition,
        competition_normalizer=_competition_normalizer(),
        participant_normalizer=participant_normalizer,
        participant_kind=ParticipantKind.TEAM,
        order_policy=ParticipantOrderPolicy.ORDERED,
    )

    assert result.evidence is None
    assert result.diagnostics[0].reason is EventMatchReason.UNRESOLVED_PARTICIPANT


def test_source_event_must_reference_supplied_competition() -> None:
    competition = SourceCompetition(
        external_id="epl",
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
        season="2026/27",
    )
    event = SourceEvent(
        external_id="event",
        sport=Sport.FOOTBALL,
        competition_external_id="other",
        participants=(SourceParticipant("team", "Team"),),
        scheduled_start=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
    )

    result = prepare_event_evidence(
        provider_id=ProviderId("provider:test"),
        event=event,
        competition=competition,
        competition_normalizer=_competition_normalizer(),
        participant_normalizer=ParticipantNormalizer(()),
        participant_kind=ParticipantKind.TEAM,
        order_policy=ParticipantOrderPolicy.ORDERED,
    )

    assert result.evidence is None
    assert result.diagnostics[0].reason is EventMatchReason.SOURCE_COMPETITION_MISMATCH
