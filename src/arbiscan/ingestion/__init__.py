"""Provider ingestion primitives."""

from arbiscan.ingestion.collector import (
    IngestedSnapshot,
    IngestionBatch,
    IngestionIssue,
    collect_snapshots,
)
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
    "IngestedSnapshot",
    "IngestionBatch",
    "IngestionIssue",
    "LiveQuoteStore",
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
    "collect_snapshots",
]
