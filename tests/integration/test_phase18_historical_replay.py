"""Phase 18 persistence-to-replay integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from arbiscan.backtesting import BacktestConfig, HistoricalQuoteCorpus, run_backtest
from arbiscan.domain import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventStatus,
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    OddsQuote,
    Participant,
    ParticipantId,
    ParticipantKind,
    ProviderId,
    QuoteId,
    QuoteStatus,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
)
from arbiscan.matching import CanonicalRegistry
from arbiscan.persistence import SqliteAuditStore

T0 = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
EVENT_ID = EventId("event:phase18:integration")
MARKET_ID = MarketId("market:phase18:integration")
OVER = SelectionId("selection:phase18:integration:over")
UNDER = SelectionId("selection:phase18:integration:under")


def _registry() -> CanonicalRegistry:
    competition = Competition(
        id=CompetitionId("competition:phase18:integration"),
        sport=Sport.FOOTBALL,
        name="Replay Integration League",
        region="BE",
        season="2026",
    )
    participants = (
        Participant(
            id=ParticipantId("participant:phase18:integration:a"),
            sport=Sport.FOOTBALL,
            name="A",
            kind=ParticipantKind.TEAM,
        ),
        Participant(
            id=ParticipantId("participant:phase18:integration:b"),
            sport=Sport.FOOTBALL,
            name="B",
            kind=ParticipantKind.TEAM,
        ),
    )
    event = Event(
        id=EVENT_ID,
        sport=Sport.FOOTBALL,
        competition=competition,
        participants=participants,
        scheduled_start=T0 + timedelta(hours=1),
        status=EventStatus.SCHEDULED,
    )
    market = Market(
        id=MARKET_ID,
        event_id=EVENT_ID,
        kind=MarketKind.TOTAL_POINTS,
        period=MarketPeriod.FULL_EVENT,
        line=Decimal("2.5"),
    )
    selections = (
        Selection(id=OVER, market_id=MARKET_ID, kind=SelectionKind.OVER),
        Selection(id=UNDER, market_id=MARKET_ID, kind=SelectionKind.UNDER),
    )
    return CanonicalRegistry(
        competitions=(competition,),
        participants=participants,
        events=(event,),
        markets=(market,),
        selections=selections,
    )


def _quote(selection: SelectionId, odds: str, *, provider: str, at: datetime) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:phase18:integration:{provider}:{selection.value}:{at.timestamp()}"),
        provider_id=ProviderId(provider),
        event_id=EVENT_ID,
        market_id=MARKET_ID,
        selection_id=selection,
        decimal_price=Decimal(odds),
        source_event_id="source:event",
        source_market_id="source:market",
        source_selection_id=selection.value,
        source_timestamp=at,
        ingested_at=at,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{provider}:{selection.value}:{at.isoformat()}",
    )


def test_persisted_canonical_history_replays_reproducibly(tmp_path: Path) -> None:
    store = SqliteAuditStore(tmp_path / "phase18.db")
    store.migrate()
    quotes = (
        _quote(OVER, "2.20", provider="provider:a", at=T0),
        _quote(UNDER, "2.20", provider="provider:b", at=T0),
        _quote(
            OVER,
            "1.80",
            provider="provider:a",
            at=T0 + timedelta(seconds=10),
        ),
    )
    for quote in reversed(quotes):
        store.persist_quote(quote)

    corpus = HistoricalQuoteCorpus.from_quotes(store.load_quotes())
    config = BacktestConfig(freshness_window=timedelta(seconds=30))

    first = run_backtest(corpus, registry=_registry(), config=config)
    second = run_backtest(corpus, registry=_registry(), config=config)

    assert first.summary == second.summary
    assert first.detections == second.detections
    assert first.summary.theoretical_detection_count == 1
    assert first.summary.total_opportunity_duration == timedelta(seconds=10)
