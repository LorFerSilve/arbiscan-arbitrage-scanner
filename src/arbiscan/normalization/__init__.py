"""Source-to-canonical normalization primitives."""

from arbiscan.normalization.aliases import (
    CompetitionAlias,
    CompetitionNormalizer,
    ParticipantAlias,
    ParticipantNormalizer,
    SportAlias,
    SportNormalizer,
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
    "MarketAlias",
    "MarketNormalizer",
    "MarketSemantic",
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
    "normalize_alias_key",
    "normalize_odds",
    "normalize_source_snapshot",
]
