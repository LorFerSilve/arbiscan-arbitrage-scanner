"""Deterministic cross-provider identity primitives."""

from arbiscan.matching.catalog import CanonicalRegistry, StaticCanonicalIdHooks
from arbiscan.matching.event_matcher import EventMatcher
from arbiscan.matching.hooks import MatchedCanonicalIdHooks
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

__all__ = [
    "CanonicalEventMatchMetadata",
    "CanonicalRegistry",
    "EventMatchCandidate",
    "EventMatchConfig",
    "EventMatchDecision",
    "EventMatchDiagnostic",
    "EventMatchReason",
    "EventMatchStatus",
    "EventMatcher",
    "MatchedCanonicalIdHooks",
    "NormalizedEventEvidence",
    "ParticipantOrderPolicy",
    "StaticCanonicalIdHooks",
]
