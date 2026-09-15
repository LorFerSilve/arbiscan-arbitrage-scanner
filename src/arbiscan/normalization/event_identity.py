"""Prepare canonical event evidence for the Phase-8 matcher."""

from __future__ import annotations

from dataclasses import dataclass

from arbiscan.domain import ParticipantId, ParticipantKind, ProviderId
from arbiscan.matching.models import (
    EventMatchDiagnostic,
    EventMatchReason,
    NormalizedEventEvidence,
    ParticipantOrderPolicy,
)
from arbiscan.normalization.aliases import CompetitionNormalizer, ParticipantNormalizer
from arbiscan.normalization.resolution import ResolutionStatus
from arbiscan.providers.models import SourceCompetition, SourceEvent


@dataclass(frozen=True, slots=True)
class EventEvidencePreparation:
    """Prepared event evidence or explicit fail-closed normalization diagnostics."""

    evidence: NormalizedEventEvidence | None
    diagnostics: tuple[EventMatchDiagnostic, ...]

    def __post_init__(self) -> None:
        diagnostics = tuple(self.diagnostics)
        if self.evidence is not None and not isinstance(self.evidence, NormalizedEventEvidence):
            raise ValueError("evidence must be NormalizedEventEvidence")
        if any(not isinstance(item, EventMatchDiagnostic) for item in diagnostics):
            raise ValueError("diagnostics must contain EventMatchDiagnostic values")
        if self.evidence is None and not diagnostics:
            raise ValueError("failed preparation requires at least one diagnostic")
        object.__setattr__(self, "diagnostics", diagnostics)


def prepare_event_evidence(
    *,
    provider_id: ProviderId,
    event: SourceEvent,
    competition: SourceCompetition,
    competition_normalizer: CompetitionNormalizer,
    participant_normalizer: ParticipantNormalizer,
    participant_kind: ParticipantKind,
    order_policy: ParticipantOrderPolicy,
    round_or_stage: str | None = None,
    venue: str | None = None,
) -> EventEvidencePreparation:
    """Resolve provider competition/participants before any cross-event comparison.

    This function intentionally performs no string-similarity matching.  Phase-7
    explicit alias catalogs must resolve every identity first; otherwise the event
    is not eligible for Phase-8 candidate scoring.
    """
    if not isinstance(provider_id, ProviderId):
        raise ValueError("provider_id must be ProviderId")
    if not isinstance(event, SourceEvent):
        raise ValueError("event must be SourceEvent")
    if not isinstance(competition, SourceCompetition):
        raise ValueError("competition must be SourceCompetition")
    if not isinstance(competition_normalizer, CompetitionNormalizer):
        raise ValueError("competition_normalizer must be CompetitionNormalizer")
    if not isinstance(participant_normalizer, ParticipantNormalizer):
        raise ValueError("participant_normalizer must be ParticipantNormalizer")
    if not isinstance(participant_kind, ParticipantKind):
        raise ValueError("participant_kind must be ParticipantKind")
    if not isinstance(order_policy, ParticipantOrderPolicy):
        raise ValueError("order_policy must be ParticipantOrderPolicy")

    if (
        event.competition_external_id != competition.external_id
        or event.sport is not competition.sport
    ):
        return EventEvidencePreparation(
            evidence=None,
            diagnostics=(
                EventMatchDiagnostic(
                    reason=EventMatchReason.SOURCE_COMPETITION_MISMATCH,
                    detail=(
                        "source event competition reference or sport does not match the supplied "
                        "source competition record"
                    ),
                ),
            ),
        )

    competition_resolution = competition_normalizer.resolve(
        competition.name,
        sport=event.sport,
        provider_id=provider_id,
        region=competition.region,
        season=competition.season,
    )
    if competition_resolution.status is not ResolutionStatus.RESOLVED:
        reason = (
            EventMatchReason.AMBIGUOUS_COMPETITION
            if competition_resolution.status is ResolutionStatus.AMBIGUOUS
            else EventMatchReason.UNRESOLVED_COMPETITION
        )
        return EventEvidencePreparation(
            evidence=None,
            diagnostics=(
                EventMatchDiagnostic(
                    reason=reason,
                    detail=competition_resolution.detail,
                ),
            ),
        )

    competition_id = competition_resolution.value
    if competition_id is None:
        raise AssertionError("resolved competition must expose a canonical ID")

    participant_ids: list[ParticipantId] = []
    diagnostics: list[EventMatchDiagnostic] = []
    for participant in event.participants:
        resolution = participant_normalizer.resolve(
            participant.name,
            sport=event.sport,
            kind=participant_kind,
            provider_id=provider_id,
            competition_id=competition_id,
            region=competition.region,
        )
        if resolution.status is ResolutionStatus.RESOLVED:
            if resolution.value is None:
                raise AssertionError("resolved participant must expose a canonical ID")
            participant_ids.append(resolution.value)
            continue
        reason = (
            EventMatchReason.AMBIGUOUS_PARTICIPANT
            if resolution.status is ResolutionStatus.AMBIGUOUS
            else EventMatchReason.UNRESOLVED_PARTICIPANT
        )
        diagnostics.append(
            EventMatchDiagnostic(
                reason=reason,
                detail=f"{participant.external_id}: {resolution.detail}",
            )
        )

    if diagnostics:
        return EventEvidencePreparation(evidence=None, diagnostics=tuple(diagnostics))

    return EventEvidencePreparation(
        evidence=NormalizedEventEvidence(
            provider_id=provider_id,
            external_event_id=event.external_id,
            sport=event.sport,
            competition_id=competition_id,
            participant_ids=tuple(participant_ids),
            scheduled_start=event.scheduled_start,
            order_policy=order_policy,
            round_or_stage=round_or_stage,
            venue=venue,
        ),
        diagnostics=(),
    )
