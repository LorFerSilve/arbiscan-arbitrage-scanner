"""Review regressions for Phase-9 market-book eligibility."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.domain import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventStatus,
    Market,
    MarketId,
    MarketKind,
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
from arbiscan.marketbook import MarketBookDiagnosticCode, build_market_books
from arbiscan.matching import CanonicalRegistry

AS_OF = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def _fixture() -> tuple[CanonicalRegistry, Event, Market, Selection, Selection]:
    first = Participant(
        id=ParticipantId("participant:first"),
        sport=Sport.TENNIS,
        name="First Player",
        kind=ParticipantKind.INDIVIDUAL,
    )
    second = Participant(
        id=ParticipantId("participant:second"),
        sport=Sport.TENNIS,
        name="Second Player",
        kind=ParticipantKind.INDIVIDUAL,
    )
    competition = Competition(
        id=CompetitionId("competition:test-tennis"),
        sport=Sport.TENNIS,
        name="Test Tennis",
    )
    event = Event(
        id=EventId("event:test-tennis"),
        sport=Sport.TENNIS,
        competition=competition,
        participants=(first, second),
        scheduled_start=datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
    )
    market = Market(
        id=MarketId("market:test-tennis:winner"),
        event_id=event.id,
        kind=MarketKind.MATCH_WINNER_2_WAY,
    )
    first_selection = Selection(
        id=SelectionId("selection:test-tennis:first"),
        market_id=market.id,
        kind=SelectionKind.PARTICIPANT,
        participant_id=first.id,
    )
    second_selection = Selection(
        id=SelectionId("selection:test-tennis:second"),
        market_id=market.id,
        kind=SelectionKind.PARTICIPANT,
        participant_id=second.id,
    )
    return (
        CanonicalRegistry(
            competitions=(competition,),
            participants=(first, second),
            events=(event,),
            markets=(market,),
            selections=(first_selection, second_selection),
        ),
        event,
        market,
        first_selection,
        second_selection,
    )


def _quote(
    *,
    provider: str,
    event: Event,
    market: Market,
    selection: Selection,
    price: str,
    source_timestamp: datetime,
    ingested_at: datetime,
) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:{provider}:{selection.id.value}"),
        provider_id=ProviderId(f"provider:{provider}"),
        event_id=event.id,
        market_id=market.id,
        selection_id=selection.id,
        decimal_price=Decimal(price),
        source_event_id=f"{provider}:event",
        source_market_id=f"{provider}:market",
        source_selection_id=f"{provider}:selection",
        source_timestamp=source_timestamp,
        ingested_at=ingested_at,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{provider}:{selection.id.value}",
    )


def test_future_ingestion_cannot_be_masked_by_historical_source_timestamp() -> None:
    registry, event, market, first, second = _fixture()
    valid_first = _quote(
        provider="valid-first",
        event=event,
        market=market,
        selection=first,
        price="2.00",
        source_timestamp=AS_OF - timedelta(seconds=30),
        ingested_at=AS_OF - timedelta(seconds=10),
    )
    valid_second = _quote(
        provider="valid-second",
        event=event,
        market=market,
        selection=second,
        price="2.10",
        source_timestamp=AS_OF - timedelta(seconds=30),
        ingested_at=AS_OF - timedelta(seconds=10),
    )
    unavailable_high_price = _quote(
        provider="future-ingestion",
        event=event,
        market=market,
        selection=first,
        price="9.00",
        source_timestamp=AS_OF - timedelta(seconds=20),
        ingested_at=AS_OF + timedelta(seconds=5),
    )

    result = build_market_books(
        (valid_first, valid_second, unavailable_high_price),
        registry=registry,
        as_of=AS_OF,
        freshness_window=timedelta(minutes=2),
    )

    selected_first = next(
        outcome.quote for outcome in result.books[0].outcomes if outcome.selection.id == first.id
    )
    assert selected_first == valid_first
    assert MarketBookDiagnosticCode.FUTURE_INGESTION in {
        diagnostic.code for diagnostic in result.diagnostics
    }
