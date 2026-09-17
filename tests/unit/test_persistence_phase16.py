"""Phase 16.2 persistence regression tests for multi-source quote provenance."""

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
)
from arbiscan.persistence import SqliteAuditStore


def test_persisted_quote_indexes_price_and_source_provider_separately(tmp_path: Path) -> None:
    database = tmp_path / "phase16.sqlite3"
    store = SqliteAuditStore(database)
    store.migrate()
    quote = OddsQuote(
        id=QuoteId("quote:phase16-persistence"),
        provider_id=ProviderId("bookmaker:shared"),
        source_provider_id=ProviderId("provider:oddspapi"),
        event_id=EventId("event:phase16"),
        market_id=MarketId("market:phase16"),
        selection_id=SelectionId("selection:phase16"),
        decimal_price=Decimal("2.05"),
        source_event_id="external-event",
        source_market_id="external-market",
        source_selection_id="external-selection",
        ingested_at=datetime(2026, 9, 17, 0, 0, tzinfo=UTC),
        status=QuoteStatus.ACTIVE,
        trace_id="trace:phase16-persistence",
    )

    store.persist_quote(quote)

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT provider_id, source_provider_id FROM canonical_snapshots "
            "WHERE entity_type = 'odds_quote' AND entity_id = ?",
            (quote.id.value,),
        ).fetchone()
        migrations = {
            version for (version,) in connection.execute("SELECT version FROM schema_migrations")
        }

    assert row == ("bookmaker:shared", "provider:oddspapi")
    assert migrations == {1, 2}
