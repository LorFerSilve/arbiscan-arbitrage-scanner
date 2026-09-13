"""Provider adapter contract and deterministic testing implementations."""

from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.errors import (
    ProviderContractError,
    ProviderError,
    ProviderErrorKind,
)
from arbiscan.providers.fake import FakeProvider, FakeProviderFixtures
from arbiscan.providers.models import (
    CanonicalIdHooks,
    OddsSnapshot,
    ProviderCapabilities,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthState,
    ProviderOperation,
    RateLimitSnapshot,
    SourceCompetition,
    SourceEvent,
    SourceMarket,
    SourceOddsFormat,
    SourceParticipant,
    SourceSelectionQuote,
)
from arbiscan.providers.resilience import ProviderCallPolicy, ProviderExecutor
from arbiscan.providers.synthetic import (
    PHASE5_AS_OF,
    PHASE5_FRESHNESS_WINDOW,
    SyntheticScenario,
    build_phase5_synthetic_scenario,
)

__all__ = [
    "PHASE5_AS_OF",
    "PHASE5_FRESHNESS_WINDOW",
    "CanonicalIdHooks",
    "FakeProvider",
    "FakeProviderFixtures",
    "OddsSnapshot",
    "ProviderAdapter",
    "ProviderCallPolicy",
    "ProviderCapabilities",
    "ProviderCapability",
    "ProviderContractError",
    "ProviderError",
    "ProviderErrorKind",
    "ProviderExecutor",
    "ProviderHealth",
    "ProviderHealthState",
    "ProviderOperation",
    "RateLimitSnapshot",
    "SourceCompetition",
    "SourceEvent",
    "SourceMarket",
    "SourceOddsFormat",
    "SourceParticipant",
    "SourceSelectionQuote",
    "SyntheticScenario",
    "build_phase5_synthetic_scenario",
]
