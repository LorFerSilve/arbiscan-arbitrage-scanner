"""Provider ingestion primitives."""

from arbiscan.ingestion.collector import (
    IngestedSnapshot,
    IngestionBatch,
    IngestionIssue,
    collect_snapshots,
)
from arbiscan.ingestion.multisource import (
    ConsolidationDiagnostic,
    ConsolidationDiagnosticCode,
    ConsolidationResult,
    PriceSlotKey,
    SourceObservationKey,
    consolidate_quotes,
)
from arbiscan.ingestion.multisource_state import MultiSourceLiveQuoteStore
from arbiscan.ingestion.realtime import (
    LiveQuoteStore,
    ProviderIngestionHealth,
    ProviderPollMetrics,
    ProviderRateGate,
    QuoteKey,
    QuoteStoreApplyResult,
    QuoteStoreDiagnostic,
    QuoteStoreDiagnosticCode,
    QuoteStoreEvictionResult,
    QuoteVersion,
    RealtimeIngestionBatch,
    RealtimeIngestionPolicy,
    RealtimeIngestionRuntime,
)

__all__ = [
    "ConsolidationDiagnostic",
    "ConsolidationDiagnosticCode",
    "ConsolidationResult",
    "IngestedSnapshot",
    "IngestionBatch",
    "IngestionIssue",
    "LiveQuoteStore",
    "MultiSourceLiveQuoteStore",
    "PriceSlotKey",
    "ProviderIngestionHealth",
    "ProviderPollMetrics",
    "ProviderRateGate",
    "QuoteKey",
    "QuoteStoreApplyResult",
    "QuoteStoreDiagnostic",
    "QuoteStoreDiagnosticCode",
    "QuoteStoreEvictionResult",
    "QuoteVersion",
    "RealtimeIngestionBatch",
    "RealtimeIngestionPolicy",
    "RealtimeIngestionRuntime",
    "SourceObservationKey",
    "collect_snapshots",
    "consolidate_quotes",
]
