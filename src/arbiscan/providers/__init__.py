"""Provider adapter contract and supported provider implementations."""

from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.errors import (
    ProviderContractError,
    ProviderError,
    ProviderErrorKind,
)
from arbiscan.providers.fake import FakeProvider, FakeProviderFixtures
from arbiscan.providers.http import (
    AsyncHttpTransport,
    HttpResponse,
    HttpTransportError,
    UrllibAsyncHttpTransport,
)
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
from arbiscan.providers.oddspapi import (
    ODDSPAPI_PROVIDER_ID,
    OddsPapiConfig,
    OddsPapiProvider,
)
from arbiscan.providers.resilience import ProviderCallPolicy, ProviderExecutor
from arbiscan.providers.the_odds_api import (
    THE_ODDS_API_PROVIDER_ID,
    TheOddsApiConfig,
    TheOddsApiProvider,
)

__all__ = [
    "ODDSPAPI_PROVIDER_ID",
    "THE_ODDS_API_PROVIDER_ID",
    "AsyncHttpTransport",
    "CanonicalIdHooks",
    "FakeProvider",
    "FakeProviderFixtures",
    "HttpResponse",
    "HttpTransportError",
    "OddsPapiConfig",
    "OddsPapiProvider",
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
    "TheOddsApiConfig",
    "TheOddsApiProvider",
    "UrllibAsyncHttpTransport",
]
