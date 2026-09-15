"""Provider-independent models for deterministic cross-provider event matching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from arbiscan.domain import CompetitionId, EventId, ParticipantId, ProviderId, Sport


class ParticipantOrderPolicy(StrEnum):
    """Whether participant tuple order is identity-bearing for an event."""

    ORDERED = "ordered"
    UNORDERED = "unordered"


class EventMatchStatus(StrEnum):
    """Final fail-closed event-matching outcome."""

    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    REJECTED = "rejected"


class EventMatchReason(StrEnum):
    """Stable explanation codes retained with matching decisions."""

    SOURCE_COMPETITION_MISMATCH = "source_competition_mismatch"
    UNRESOLVED_COMPETITION = "unresolved_competition"
    AMBIGUOUS_COMPETITION = "ambiguous_competition"
    UNRESOLVED_PARTICIPANT = "unresolved_participant"
    AMBIGUOUS_PARTICIPANT = "ambiguous_participant"
    SPORT_MISMATCH = "sport_mismatch"
    COMPETITION_MISMATCH = "competition_mismatch"
    PARTICIPANT_MISMATCH = "participant_mismatch"
    PARTICIPANT_ORDER_MISMATCH = "participant_order_mismatch"
    START_TIME_OUTSIDE_TOLERANCE = "start_time_outside_tolerance"
    STAGE_MISMATCH = "stage_mismatch"
    VENUE_MISMATCH = "venue_mismatch"
    PROVIDER_REFERENCE_CONFLICT = "provider_reference_conflict"
    BELOW_CONFIDENCE_THRESHOLD = "below_confidence_threshold"
    AMBIGUOUS_CANDIDATES = "ambiguous_candidates"
    MATCHED = "matched"


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class EventMatchConfig:
    """Deterministic thresholds for one event-matching policy version."""

    start_time_tolerance: timedelta = timedelta(minutes=30)
    referenced_start_time_tolerance: timedelta = timedelta(hours=48)
    minimum_confidence_bps: int = 8500
    ambiguity_margin_bps: int = 250

    def __post_init__(self) -> None:
        if (
            not isinstance(self.start_time_tolerance, timedelta)
            or self.start_time_tolerance <= timedelta(0)
        ):
            raise ValueError("start_time_tolerance must be positive")
        if (
            not isinstance(self.referenced_start_time_tolerance, timedelta)
            or self.referenced_start_time_tolerance < self.start_time_tolerance
        ):
            raise ValueError(
                "referenced_start_time_tolerance must be >= start_time_tolerance"
            )
        for name, value in (
            ("minimum_confidence_bps", self.minimum_confidence_bps),
            ("ambiguity_margin_bps", self.ambiguity_margin_bps),
        ):
            if type(value) is not int or not 0 <= value <= 10_000:
                raise ValueError(f"{name} must be an integer from 0 to 10000")


@dataclass(frozen=True, slots=True)
class NormalizedEventEvidence:
    """Provider event after Phase-7 competition/participant normalization."""

    provider_id: ProviderId
    external_event_id: str
    sport: Sport
    competition_id: CompetitionId
    participant_ids: tuple[ParticipantId, ...]
    scheduled_start: datetime
    order_policy: ParticipantOrderPolicy
    round_or_stage: str | None = None
    venue: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise ValueError("provider_id must be ProviderId")
        if not isinstance(self.external_event_id, str) or not self.external_event_id.strip():
            raise ValueError("external_event_id must be non-empty text")
        if not isinstance(self.sport, Sport):
            raise ValueError("sport must be Sport")
        if not isinstance(self.competition_id, CompetitionId):
            raise ValueError("competition_id must be CompetitionId")
        participants = tuple(self.participant_ids)
        if not participants or any(
            not isinstance(participant_id, ParticipantId) for participant_id in participants
        ):
            raise ValueError("participant_ids must contain ParticipantId values")
        if len(set(participants)) != len(participants):
            raise ValueError("participant_ids must be unique")
        if not isinstance(self.order_policy, ParticipantOrderPolicy):
            raise ValueError("order_policy must be ParticipantOrderPolicy")
        object.__setattr__(self, "external_event_id", self.external_event_id.strip())
        object.__setattr__(self, "participant_ids", participants)
        object.__setattr__(
            self,
            "scheduled_start",
            _aware_utc(self.scheduled_start, field_name="scheduled_start"),
        )
        object.__setattr__(
            self,
            "round_or_stage",
            _optional_text(self.round_or_stage, field_name="round_or_stage"),
        )
        object.__setattr__(self, "venue", _optional_text(self.venue, field_name="venue"))


@dataclass(frozen=True, slots=True)
class CanonicalEventMatchMetadata:
    """Optional canonical matching evidence not carried by the core Event schema."""

    event_id: EventId
    round_or_stage: str | None = None
    venue: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId):
            raise ValueError("event_id must be EventId")
        object.__setattr__(
            self,
            "round_or_stage",
            _optional_text(self.round_or_stage, field_name="round_or_stage"),
        )
        object.__setattr__(self, "venue", _optional_text(self.venue, field_name="venue"))


@dataclass(frozen=True, slots=True)
class EventMatchCandidate:
    """One surviving canonical candidate with deterministic confidence evidence."""

    event_id: EventId
    confidence_bps: int
    start_delta: timedelta
    explicit_provider_reference: bool
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId):
            raise ValueError("event_id must be EventId")
        if type(self.confidence_bps) is not int or not 0 <= self.confidence_bps <= 10_000:
            raise ValueError("confidence_bps must be an integer from 0 to 10000")
        if not isinstance(self.start_delta, timedelta) or self.start_delta < timedelta(0):
            raise ValueError("start_delta must be a non-negative timedelta")
        evidence = tuple(self.evidence)
        if any(not isinstance(item, str) or not item.strip() for item in evidence):
            raise ValueError("candidate evidence must contain non-empty text")
        object.__setattr__(self, "evidence", evidence)


@dataclass(frozen=True, slots=True)
class EventMatchDiagnostic:
    """Reason one event candidate or source preparation step was rejected."""

    reason: EventMatchReason
    detail: str
    candidate_event_id: EventId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reason, EventMatchReason):
            raise ValueError("diagnostic reason must be EventMatchReason")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("diagnostic detail must be non-empty text")
        if self.candidate_event_id is not None and not isinstance(
            self.candidate_event_id, EventId
        ):
            raise ValueError("candidate_event_id must be EventId")
        object.__setattr__(self, "detail", self.detail.strip())


@dataclass(frozen=True, slots=True)
class EventMatchDecision:
    """Traceable fail-closed cross-provider event matching result."""

    status: EventMatchStatus
    matched_event_id: EventId | None
    confidence_bps: int | None
    candidates: tuple[EventMatchCandidate, ...]
    diagnostics: tuple[EventMatchDiagnostic, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, EventMatchStatus):
            raise ValueError("status must be EventMatchStatus")
        candidates = tuple(self.candidates)
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, EventMatchCandidate) for item in candidates):
            raise ValueError("candidates must contain EventMatchCandidate values")
        if any(not isinstance(item, EventMatchDiagnostic) for item in diagnostics):
            raise ValueError("diagnostics must contain EventMatchDiagnostic values")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "diagnostics", diagnostics)

        if self.status is EventMatchStatus.MATCHED:
            if self.matched_event_id is None or self.confidence_bps is None:
                raise ValueError("matched decisions require event ID and confidence")
            if not isinstance(self.matched_event_id, EventId):
                raise ValueError("matched_event_id must be EventId")
            if not 0 <= self.confidence_bps <= 10_000:
                raise ValueError("confidence_bps must be from 0 to 10000")
            return
        if self.matched_event_id is not None or self.confidence_bps is not None:
            raise ValueError("unmatched decisions cannot expose matched event or confidence")
