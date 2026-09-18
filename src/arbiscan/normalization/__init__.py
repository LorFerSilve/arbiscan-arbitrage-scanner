"""Source-to-canonical normalization primitives."""

from arbiscan.normalization.aliases import (
    CompetitionAlias,
    CompetitionNormalizer,
    ParticipantAlias,
    ParticipantNormalizer,
    SportAlias,
    SportNormalizer,
)
from arbiscan.normalization.event_identity import EventEvidencePreparation, prepare_event_evidence
from arbiscan.normalization.market_support import (
    MarketSupportDecision,
    MarketSupportStatus,
    assess_market_support,
    is_push_free_football_handicap_line,
    is_push_free_football_total_line,
)
from arbiscan.normalization.markets import MarketAlias, MarketNormalizer, MarketSemantic
from arbiscan.normalization.odds import OddsNormalizationError, normalize_odds
from arbiscan.normalization.resolution import Resolution, ResolutionStatus
from arbiscan.normalization.strict import (
    NormalizationIssue,
    NormalizationIssueCode,
    NormalizationResult,
    normalize_source_snapshot,
)
from arbiscan.normalization.text import normalize_alias_key

__all__ = [
    "CompetitionAlias",
    "CompetitionNormalizer",
    "EventEvidencePreparation",
    "MarketAlias",
    "MarketNormalizer",
    "MarketSemantic",
    "MarketSupportDecision",
    "MarketSupportStatus",
    "NormalizationIssue",
    "NormalizationIssueCode",
    "NormalizationResult",
    "OddsNormalizationError",
    "ParticipantAlias",
    "ParticipantNormalizer",
    "Resolution",
    "ResolutionStatus",
    "SportAlias",
    "SportNormalizer",
    "assess_market_support",
    "is_push_free_football_handicap_line",
    "is_push_free_football_total_line",
    "normalize_alias_key",
    "normalize_odds",
    "normalize_source_snapshot",
    "prepare_event_evidence",
]
