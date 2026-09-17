"""Phase-16.2 persistence compatibility and transport-provenance regressions."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
    dumps,
)
from arbiscan.persistence import SqliteAuditStore


def _quote(*, transport: str = "bookmaker:legacy") -> OddsQuote:
    return OddsQuote(
        id=QuoteId("quote:legacy"),
        provider_id=ProviderId("bookmaker:legacy"),
        transport_provider_id=ProviderId(transport),
        event_id=EventId("event:legacy"),
        market_id=MarketId("market:legacy"),
        selection_id=SelectionId("selection:legacy"),
        decimal_price=Decimal("2.10"),
        source_event_id="legacy-event",
        source_market_id="legacy-market",
        source_selection_id="legacy-selection",
        source_timestamp=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 9, 16, 12, 0, 1, tzinfo=UTC),
        status=QuoteStatus.ACTIVE,
        trace_id="legacy-trace",
    )


def _schema_v1_payload(quote: OddsQuote) -> str:
    encoded = cast(dict[str, object], json.loads(dumps(quote)))
    encoded["schema_version"] = 1
    payload = cast(dict[str, object], encoded["payload"])
    del payload["transport_provider_id"]
    return json.dumps(encoded, sort_keys=True, separators=(",", ":"))


def _create_v1_database(path: Path, quote: OddsQuote) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
            );
            CREATE TABLE canonical_snapshots (
                entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, event_id TEXT,
                provider_id TEXT, occurred_at TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (entity_type, entity_id)
            );
            CREATE TABLE audit_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL, action TEXT NOT NULL, recorded_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (1, ?)",
            (datetime.now(UTC).isoformat(),),
        )
        connection.execute(
            "INSERT INTO canonical_snapshots"
            "(entity_type, entity_id, event_id, provider_id, occurred_at, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "odds_quote",
                quote.id.value,
                quote.event_id.value,
                quote.provider_id.value,
                quote.ingested_at.isoformat(),
                _schema_v1_payload(quote),
            ),
        )


def test_v1_database_migration_backfills_legacy_transport_identity(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    quote = _quote()
    _create_v1_database(database, quote)

    store = SqliteAuditStore(database)
    store.migrate()

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT transport_provider_id FROM canonical_snapshots "
            "WHERE entity_type = 'odds_quote' AND entity_id = ?",
            (quote.id.value,),
        ).fetchone()
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert row == (quote.provider_id.value,)
    assert versions == [(1,), (2,)]

    # Re-persisting the semantically identical current-schema object must not be
    # treated as an ID collision merely because the stored payload is schema v1.
    store.persist_quote(quote)


def test_new_quote_persistence_indexes_transport_separately_from_price_provider(
    tmp_path: Path,
) -> None:
    database = tmp_path / "current.db"
    quote = _quote(transport="provider:aggregator-a")
    store = SqliteAuditStore(database)
    store.migrate()
    store.persist_quote(quote)

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT provider_id, transport_provider_id FROM canonical_snapshots "
            "WHERE entity_type = 'odds_quote' AND entity_id = ?",
            (quote.id.value,),
        ).fetchone()

    assert row == ("bookmaker:legacy", "provider:aggregator-a")
