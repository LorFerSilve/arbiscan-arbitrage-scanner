"""Provider ingestion primitives."""

from arbiscan.ingestion.collector import (
    IngestedSnapshot,
    IngestionBatch,
    IngestionIssue,
    collect_snapshots,
)

__all__ = [
    "IngestedSnapshot",
    "IngestionBatch",
    "IngestionIssue",
    "collect_snapshots",
]
