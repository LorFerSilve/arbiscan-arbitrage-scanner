"""Deterministic staged cross-provider event matching."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from types import MappingProxyType

from arbiscan.domain import Event, EventId
from arbiscan.matching.catalog import CanonicalRegistry
from arbiscan.matching.models import (
    CanonicalEventMatchMetadata,
    EventMatchCandidate,
    EventMatchConfig,
    EventMatchDecision,
    EventMatchDiagnostic,
    EventMatchReason,
    EventMatchStatus,
    NormalizedEventEvidence,
    ParticipantOrderPolicy,
)


def _comparison_key(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _timedelta_microseconds(value: timedelta) -> int:
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds


def _time_score(delta: timedelta, tolerance: timedelta) -> int:
    total = _timedelta_microseconds(tolerance)
    elapsed = min(_timedelta_microseconds(delta), total)
    return 2_000 * (total - elapsed) // total


@dataclass(frozen=True, slots=True)
class EventMatcher:
    """Match normalized provider evidence to one canonical event or fail closed."""

    registry: CanonicalRegistry
    config: EventMatchConfig = field(default_factory=EventMatchConfig)
    metadata: tuple[CanonicalEventMatchMetadata, ...] = ()
    cache_capacity: int = 4_096
    exhaustive_diagnostics: bool = False
    _metadata_by_id: Mapping[EventId, CanonicalEventMatchMetadata] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _decision_cache: OrderedDict[NormalizedEventEvidence, EventMatchDecision] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.registry, CanonicalRegistry):
            raise ValueError("registry must be CanonicalRegistry")
        if not isinstance(self.config, EventMatchConfig):
            raise ValueError("config must be EventMatchConfig")
        metadata = tuple(self.metadata)
        if any(not isinstance(item, CanonicalEventMatchMetadata) for item in metadata):
            raise ValueError("metadata must contain CanonicalEventMatchMetadata values")
        ids = [item.event_id for item in metadata]
        if len(set(ids)) != len(ids):
            raise ValueError("metadata may contain at most one record per event")
        if any(self.registry.event(item.event_id) is None for item in metadata):
            raise ValueError("metadata references an event outside the registry")
        if type(self.cache_capacity) is not int or self.cache_capacity < 0:
            raise ValueError("cache_capacity must be a non-negative integer")
        if type(self.exhaustive_diagnostics) is not bool:
            raise ValueError("exhaustive_diagnostics must be boolean")
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(
            self,
            "_metadata_by_id",
            MappingProxyType({item.event_id: item for item in metadata}),
        )
        object.__setattr__(self, "_decision_cache", OrderedDict())

    @property
    def cached_decision_count(self) -> int:
        """Return the current bounded cache size for diagnostics and benchmarks."""
        return len(self._decision_cache)

    def match(self, evidence: NormalizedEventEvidence) -> EventMatchDecision:
        """Return a deterministic match, reusing an exact evidence decision when cached."""
        if not isinstance(evidence, NormalizedEventEvidence):
            raise ValueError("evidence must be NormalizedEventEvidence")

        if self.cache_capacity > 0:
            cached = self._decision_cache.get(evidence)
            if cached is not None:
                self._decision_cache.move_to_end(evidence)
                return cached

        decision = self._match_uncached(evidence)
        if self.cache_capacity > 0:
            self._decision_cache[evidence] = decision
            self._decision_cache.move_to_end(evidence)
            while len(self._decision_cache) > self.cache_capacity:
                self._decision_cache.popitem(last=False)
        return decision

    def _match_uncached(self, evidence: NormalizedEventEvidence) -> EventMatchDecision:
        diagnostics: list[EventMatchDiagnostic] = []
        candidates: list[EventMatchCandidate] = []

        if self.exhaustive_diagnostics:
            candidate_events = self.registry.events
        else:
            candidate_events = self.registry.event_match_candidates(
                evidence.sport,
                evidence.competition_id,
                evidence.participant_ids,
            )
            if not candidate_events:
                diagnostics.append(self._hard_filter_diagnostic(evidence))

        for event in candidate_events:
            candidate, rejected = self._evaluate_candidate(
                evidence,
                event,
                self._metadata_by_id.get(event.id),
            )
            if candidate is not None:
                candidates.append(candidate)
            elif rejected is not None:
                diagnostics.append(rejected)

        candidates.sort(
            key=lambda item: (
                -item.confidence_bps,
                item.start_delta,
                item.event_id.value,
            )
        )
        eligible = tuple(
            candidate
            for candidate in candidates
            if candidate.confidence_bps >= self.config.minimum_confidence_bps
        )

        if not eligible:
            if candidates:
                diagnostics.extend(
                    EventMatchDiagnostic(
                        reason=EventMatchReason.BELOW_CONFIDENCE_THRESHOLD,
                        candidate_event_id=candidate.event_id,
                        detail=(
                            f"confidence {candidate.confidence_bps} bps is below required "
                            f"{self.config.minimum_confidence_bps} bps"
                        ),
                    )
                    for candidate in candidates
                )
            return EventMatchDecision(
                status=EventMatchStatus.REJECTED,
                matched_event_id=None,
                confidence_bps=None,
                candidates=tuple(candidates),
                diagnostics=tuple(diagnostics),
            )

        best = eligible[0]
        ambiguous = tuple(
            candidate
            for candidate in eligible[1:]
            if best.confidence_bps - candidate.confidence_bps <= self.config.ambiguity_margin_bps
        )
        if ambiguous:
            contenders = (best, *ambiguous)
            diagnostics.append(
                EventMatchDiagnostic(
                    reason=EventMatchReason.AMBIGUOUS_CANDIDATES,
                    detail=(
                        "multiple canonical events remain within the configured confidence "
                        f"margin of {self.config.ambiguity_margin_bps} bps"
                    ),
                )
            )
            return EventMatchDecision(
                status=EventMatchStatus.AMBIGUOUS,
                matched_event_id=None,
                confidence_bps=None,
                candidates=contenders,
                diagnostics=tuple(diagnostics),
            )

        diagnostics.append(
            EventMatchDiagnostic(
                reason=EventMatchReason.MATCHED,
                candidate_event_id=best.event_id,
                detail=f"canonical event matched at {best.confidence_bps} confidence bps",
            )
        )
        return EventMatchDecision(
            status=EventMatchStatus.MATCHED,
            matched_event_id=best.event_id,
            confidence_bps=best.confidence_bps,
            candidates=eligible,
            diagnostics=tuple(diagnostics),
        )

    def _hard_filter_diagnostic(
        self,
        evidence: NormalizedEventEvidence,
    ) -> EventMatchDiagnostic:
        if not self.registry.events_for_sport(evidence.sport):
            return EventMatchDiagnostic(
                reason=EventMatchReason.SPORT_MISMATCH,
                detail="no canonical event shares the provider sport",
            )
        if not self.registry.events_for_competition(
            evidence.sport,
            evidence.competition_id,
        ):
            return EventMatchDiagnostic(
                reason=EventMatchReason.COMPETITION_MISMATCH,
                detail="no canonical event shares the provider sport and competition",
            )
        return EventMatchDiagnostic(
            reason=EventMatchReason.PARTICIPANT_MISMATCH,
            detail=(
                "no canonical event shares the provider sport, competition, "
                "and participant identities"
            ),
        )

    def _evaluate_candidate(
        self,
        evidence: NormalizedEventEvidence,
        event: Event,
        metadata: CanonicalEventMatchMetadata | None,
    ) -> tuple[EventMatchCandidate | None, EventMatchDiagnostic | None]:
        if event.sport is not evidence.sport:
            return None, self._diagnostic(
                event.id,
                EventMatchReason.SPORT_MISMATCH,
                "canonical and provider sports differ",
            )
        if event.competition.id != evidence.competition_id:
            return None, self._diagnostic(
                event.id,
                EventMatchReason.COMPETITION_MISMATCH,
                "canonical and provider competitions differ",
            )

        canonical_participants = tuple(item.id for item in event.participants)
        if set(canonical_participants) != set(evidence.participant_ids):
            return None, self._diagnostic(
                event.id,
                EventMatchReason.PARTICIPANT_MISMATCH,
                "canonical and provider participant sets differ",
            )
        if (
            evidence.order_policy is ParticipantOrderPolicy.ORDERED
            and canonical_participants != evidence.participant_ids
        ):
            return None, self._diagnostic(
                event.id,
                EventMatchReason.PARTICIPANT_ORDER_MISMATCH,
                "participant ordering is identity-bearing and does not match",
            )

        references = tuple(
            reference
            for reference in event.provider_references
            if reference.provider_id == evidence.provider_id
        )
        exact_reference = any(
            reference.external_event_id == evidence.external_event_id for reference in references
        )
        if references and not exact_reference:
            return None, self._diagnostic(
                event.id,
                EventMatchReason.PROVIDER_REFERENCE_CONFLICT,
                "canonical event already has a different event reference for this provider",
            )

        delta = abs(event.scheduled_start - evidence.scheduled_start)
        tolerance = (
            self.config.referenced_start_time_tolerance
            if exact_reference
            else self.config.start_time_tolerance
        )
        if delta > tolerance:
            return None, self._diagnostic(
                event.id,
                EventMatchReason.START_TIME_OUTSIDE_TOLERANCE,
                f"start-time delta {delta} exceeds tolerance {tolerance}",
            )

        stage_score = 0
        venue_score = 0
        evidence_notes = [
            "sport exact",
            "competition exact",
            "participant identities exact",
            (
                "participant order exact"
                if evidence.order_policy is ParticipantOrderPolicy.ORDERED
                else "participant order intentionally non-semantic"
            ),
        ]
        if metadata is not None:
            if evidence.round_or_stage is not None and metadata.round_or_stage is not None:
                if _comparison_key(evidence.round_or_stage) != _comparison_key(
                    metadata.round_or_stage
                ):
                    return None, self._diagnostic(
                        event.id,
                        EventMatchReason.STAGE_MISMATCH,
                        "event round/stage metadata conflicts",
                    )
                stage_score = 400
                evidence_notes.append("round/stage exact")
            if evidence.venue is not None and metadata.venue is not None:
                if _comparison_key(evidence.venue) != _comparison_key(metadata.venue):
                    return None, self._diagnostic(
                        event.id,
                        EventMatchReason.VENUE_MISMATCH,
                        "event venue metadata conflicts",
                    )
                venue_score = 300
                evidence_notes.append("venue exact")

        confidence = 500 + 1_500 + 4_500 + 500
        confidence += _time_score(delta, tolerance)
        confidence += stage_score + venue_score
        if exact_reference:
            confidence += 1_000
            evidence_notes.append("explicit provider event reference exact")
        confidence = min(confidence, 10_000)
        evidence_notes.append(f"start delta {delta}")

        return (
            EventMatchCandidate(
                event_id=event.id,
                confidence_bps=confidence,
                start_delta=delta,
                explicit_provider_reference=exact_reference,
                evidence=tuple(evidence_notes),
            ),
            None,
        )

    @staticmethod
    def _diagnostic(
        event_id: EventId,
        reason: EventMatchReason,
        detail: str,
    ) -> EventMatchDiagnostic:
        return EventMatchDiagnostic(
            reason=reason,
            candidate_event_id=event_id,
            detail=detail,
        )
