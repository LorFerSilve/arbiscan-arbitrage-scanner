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
    MarketSupportPurpose,
    MarketSupportStatus,
    assess_market_support,
    is_push_free_basketball_handicap_line,
    is_push_free_basketball_total_line,
    is_push_free_football_handicap_line,
    is_push_free_football_total_line,
)
from arbiscan.normalization.markets import MarketAlias, MarketNormalizer, MarketSemantic
from arbiscan.normalization.odds import OddsNormalizationError, normalize_odds
from arbiscan.normalization.outrights import (
    OutrightEvaluationProfile,
    OutrightMathEligibility,
    assess_generic_outright_math,
)
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
    "MarketSupportPurpose",
    "MarketSupportStatus",
    "NormalizationIssue",
    "NormalizationIssueCode",
    "NormalizationResult",
    "OddsNormalizationError",
    "OutrightEvaluationProfile",
    "OutrightMathEligibility",
    "ParticipantAlias",
    "ParticipantNormalizer",
    "Resolution",
    "ResolutionStatus",
    "SportAlias",
    "SportNormalizer",
    "assess_generic_outright_math",
    "assess_market_support",
    "is_push_free_basketball_handicap_line",
    "is_push_free_basketball_total_line",
    "is_push_free_football_handicap_line",
    "is_push_free_football_total_line",
    "normalize_alias_key",
    "normalize_odds",
    "normalize_source_snapshot",
    "prepare_event_evidence",
]
