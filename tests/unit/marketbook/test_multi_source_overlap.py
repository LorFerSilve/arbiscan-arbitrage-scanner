"""Phase 16.2 regression tests for multi-source bookmaker overlap consolidation."""

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
from arbiscan.marketbook import MarketBookDiagnosticCode, build_market_books
from arbiscan.matching import CanonicalRegistry

AS_OF = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=2)
THE_ODDS_API = ProviderId("provider:the-odds-api")
ODDSPAPI = ProviderId("provider:oddspapi")
SHARED_BOOKMAKER = ProviderId("bookmaker:shared")
ALTERNATIVE_BOOKMAKER = ProviderId("bookmaker:alternative")


def _registry() -> tuple[CanonicalRegistry, Event, Market, tuple[Selection, Selection]]:
    player_a = Participant(
        id=ParticipantId("participant:a"),
        sport=Sport.TENNIS,
        name="Player A",
        kind=ParticipantKind.INDIVIDUAL,
    )
    player_b = Participant(
        id=ParticipantId("participant:b"),
        sport=Sport.TENNIS,
        name="Player B",
        kind=ParticipantKind.INDIVIDUAL,
    )
    competition = Competition(
        id=CompetitionId("competition:test"),
        sport=Sport.TENNIS,
        name="Test Open",
    )
    event = Event(
        id=EventId("event:test"),
        sport=Sport.TENNIS,
        competition=competition,
        participants=(player_a, player_b),
        scheduled_start=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
    )
    market = Market(
        id=MarketId("market:test:winner"),
        event_id=event.id,
        kind=MarketKind.MATCH_WINNER_2_WAY,
        period=MarketPeriod.FULL_EVENT,
    )
    selections = (
        Selection(
            id=SelectionId("selection:a"),
            market_id=market.id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=player_a.id,
        ),
        Selection(
            id=SelectionId("selection:b"),
            market_id=market.id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=player_b.id,
        ),
    )
    return (
        CanonicalRegistry(
            competitions=(competition,),
            participants=(player_a, player_b),
            events=(event,),
            markets=(market,),
            selections=selections,
        ),
        event,
        market,
        selections,
    )


def _quote(
    *,
    price_provider: ProviderId,
    source_provider: ProviderId,
    event: Event,
    market: Market,
    selection: Selection,
    price: str,
    seconds_old: int,
    suffix: str,
) -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:{suffix}"),
        provider_id=price_provider,
        source_provider_id=source_provider,
        event_id=event.id,
        market_id=market.id,
        selection_id=selection.id,
        decimal_price=Decimal(price),
        source_event_id=f"{source_provider.value}:event",
        source_market_id=f"{source_provider.value}:market",
        source_selection_id=f"{source_provider.value}:{selection.id.value}",
        source_timestamp=AS_OF - timedelta(seconds=seconds_old),
        ingested_at=AS_OF,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{suffix}",
    )


def _other_outcome(event: Event, market: Market, selection: Selection) -> OddsQuote:
    return _quote(
        price_provider=ALTERNATIVE_BOOKMAKER,
        source_provider=THE_ODDS_API,
        event=event,
        market=market,
        selection=selection,
        price="2.00",
        seconds_old=5,
        suffix="other-outcome",
    )


def test_newest_source_observation_wins_before_price_competition() -> None:
    registry, event, market, selections = _registry()
    older_high = _quote(
        price_provider=SHARED_BOOKMAKER,
        source_provider=THE_ODDS_API,
        event=event,
        market=market,
        selection=selections[0],
        price="2.40",
        seconds_old=15,
        suffix="older-high",
    )
    newer_low = _quote(
        price_provider=SHARED_BOOKMAKER,
        source_provider=ODDSPAPI,
        event=event,
        market=market,
        selection=selections[0],
        price="2.10",
        seconds_old=5,
        suffix="newer-low",
    )

    result = build_market_books(
        (older_high, newer_low, _other_outcome(event, market, selections[1])),
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    assert len(result.books) == 1
    selected = next(
        quote for quote in result.books[0].quotes if quote.selection_id == selections[0].id
    )
    assert selected.decimal_price == Decimal("2.10")
    assert selected.provider_id == SHARED_BOOKMAKER
    assert selected.source_provider_id == ODDSPAPI


def test_equivalent_equal_time_overlap_is_deterministic_and_counted_once() -> None:
    registry, event, market, selections = _registry()
    the_odds = _quote(
        price_provider=SHARED_BOOKMAKER,
        source_provider=THE_ODDS_API,
        event=event,
        market=market,
        selection=selections[0],
        price="2.20",
        seconds_old=5,
        suffix="equivalent-the-odds",
    )
    oddspapi = _quote(
        price_provider=SHARED_BOOKMAKER,
        source_provider=ODDSPAPI,
        event=event,
        market=market,
        selection=selections[0],
        price="2.20",
        seconds_old=5,
        suffix="equivalent-oddspapi",
    )
    other = _other_outcome(event, market, selections[1])

    forward = build_market_books(
        (the_odds, oddspapi, other),
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )
    reverse = build_market_books(
        (other, oddspapi, the_odds),
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    assert len(forward.books) == len(reverse.books) == 1
    forward_quote = next(
        quote for quote in forward.books[0].quotes if quote.selection_id == selections[0].id
    )
    reverse_quote = next(
        quote for quote in reverse.books[0].quotes if quote.selection_id == selections[0].id
    )
    assert forward_quote.id == reverse_quote.id
    assert forward_quote.provider_id == SHARED_BOOKMAKER
    assert forward_quote.source_provider_id == ODDSPAPI
    assert len(forward.books[0].quotes) == 2


def test_conflicting_equal_time_overlap_fails_closed_for_price_provider_slot() -> None:
    registry, event, market, selections = _registry()
    the_odds = _quote(
        price_provider=SHARED_BOOKMAKER,
        source_provider=THE_ODDS_API,
        event=event,
        market=market,
        selection=selections[0],
        price="2.20",
        seconds_old=5,
        suffix="conflict-the-odds",
    )
    oddspapi = _quote(
        price_provider=SHARED_BOOKMAKER,
        source_provider=ODDSPAPI,
        event=event,
        market=market,
        selection=selections[0],
        price="2.30",
        seconds_old=5,
        suffix="conflict-oddspapi",
    )

    result = build_market_books(
        (the_odds, oddspapi, _other_outcome(event, market, selections[1])),
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    assert result.books == ()
    conflicts = tuple(
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.code is MarketBookDiagnosticCode.CONFLICTING_SOURCE_OBSERVATIONS
    )
    assert len(conflicts) == 2
    assert {diagnostic.source_provider_id for diagnostic in conflicts} == {
        THE_ODDS_API,
        ODDSPAPI,
    }
    assert all(diagnostic.provider_id == SHARED_BOOKMAKER for diagnostic in conflicts)
    assert MarketBookDiagnosticCode.INCOMPLETE_MARKET in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_conflicting_bookmaker_does_not_poison_an_independent_bookmaker() -> None:
    registry, event, market, selections = _registry()
    conflict_a = _quote(
        price_provider=SHARED_BOOKMAKER,
        source_provider=THE_ODDS_API,
        event=event,
        market=market,
        selection=selections[0],
        price="2.20",
        seconds_old=5,
        suffix="slot-conflict-a",
    )
    conflict_b = _quote(
        price_provider=SHARED_BOOKMAKER,
        source_provider=ODDSPAPI,
        event=event,
        market=market,
        selection=selections[0],
        price="2.30",
        seconds_old=5,
        suffix="slot-conflict-b",
    )
    independent = _quote(
        price_provider=ALTERNATIVE_BOOKMAKER,
        source_provider=THE_ODDS_API,
        event=event,
        market=market,
        selection=selections[0],
        price="2.05",
        seconds_old=4,
        suffix="independent",
    )

    result = build_market_books(
        (conflict_a, conflict_b, independent, _other_outcome(event, market, selections[1])),
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    assert len(result.books) == 1
    selected = next(
        quote for quote in result.books[0].quotes if quote.selection_id == selections[0].id
    )
    assert selected.id == independent.id
