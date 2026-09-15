from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from arbiscan.domain.enums import QuoteStatus
from arbiscan.domain.identifiers import (
    EventId,
    MarketId,
    OpportunityId,
    ProviderId,
    QuoteId,
    SelectionId,
)
from arbiscan.domain.models import OddsQuote, Opportunity
from arbiscan.persistence import PersistenceError, SqliteAuditStore


def _quote(number: int, *, at: datetime, price: str = "2.10") -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote-{number}"),
        provider_id=ProviderId(f"provider-{number}"),
        event_id=EventId("event-1"),
        market_id=MarketId("market-1"),
        selection_id=SelectionId(f"selection-{number}"),
        decimal_price=Decimal(price),
        source_event_id="source-event",
        source_market_id="source-market",
        source_selection_id=f"source-selection-{number}",
        ingested_at=at,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace-{number}",
    )


def _opportunity(quotes: tuple[OddsQuote, ...], *, at: datetime) -> Opportunity:
    return Opportunity(
        id=OpportunityId("opportunity-1"),
        event_id=EventId("event-1"),
        market_id=MarketId("market-1"),
        quote_ids=tuple(quote.id for quote in quotes),
        implied_probability_sum=Decimal("0.95238095238095238095"),
        theoretical_profit_margin=Decimal("0.05"),
        detected_at=at,
    )


def _assert_persistence_error(action: object, expected: str) -> None:
    try:
        callable_action = action
        assert callable(callable_action)
        callable_action()
    except PersistenceError as exc:
        assert expected in str(exc)
    else:
        raise AssertionError("expected PersistenceError")


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    store = SqliteAuditStore(tmp_path / "arbiscan.db")
    store.migrate()
    store.migrate()


def test_opportunity_can_be_reconstructed_from_persisted_evidence(tmp_path: Path) -> None:
    store = SqliteAuditStore(tmp_path / "arbiscan.db")
    store.migrate()
    now = datetime(2026, 9, 15, 16, 0, tzinfo=UTC)
    quotes = (_quote(1, at=now), _quote(2, at=now))
    opportunity = _opportunity(quotes, at=now)
    store.persist_opportunity(opportunity, quotes)
    store.persist_opportunity(opportunity, quotes)

    evidence = store.reconstruct_opportunity("opportunity-1")

    assert evidence.opportunity == opportunity
    assert evidence.quotes == quotes
    assert evidence.stake_plan is None


def test_persist_opportunity_rejects_incomplete_evidence(tmp_path: Path) -> None:
    store = SqliteAuditStore(tmp_path / "arbiscan.db")
    store.migrate()
    now = datetime(2026, 9, 15, 16, 0, tzinfo=UTC)
    quotes = (_quote(1, at=now), _quote(2, at=now))
    opportunity = _opportunity(quotes, at=now)

    _assert_persistence_error(
        lambda: store.persist_opportunity(opportunity, quotes[:1]),
        "exactly its referenced quotes",
    )


def test_same_id_with_different_payload_fails_closed(tmp_path: Path) -> None:
    store = SqliteAuditStore(tmp_path / "arbiscan.db")
    store.migrate()
    now = datetime(2026, 9, 15, 16, 0, tzinfo=UTC)
    store.persist_quote(_quote(1, at=now))

    _assert_persistence_error(
        lambda: store.persist_quote(_quote(1, at=now, price="2.20")), "ID collision"
    )


def test_retention_preserves_quotes_referenced_by_opportunities(tmp_path: Path) -> None:
    store = SqliteAuditStore(tmp_path / "arbiscan.db")
    store.migrate()
    old = datetime(2026, 9, 1, tzinfo=UTC)
    quotes = (_quote(1, at=old), _quote(2, at=old))
    store.persist_opportunity(_opportunity(quotes, at=old), quotes)
    store.persist_quote(_quote(3, at=old))

    removed = store.purge_quotes_before(old + timedelta(days=1))

    assert removed == 1
    assert store.reconstruct_opportunity("opportunity-1").quotes == quotes
