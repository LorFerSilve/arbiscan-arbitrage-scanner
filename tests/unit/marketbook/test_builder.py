"""Adversarial tests for Phase-9 canonical market-book construction."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

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
from arbiscan.marketbook import (
    MarketBookDiagnosticCode,
    ProviderBookPolicy,
    build_market_books,
)
from arbiscan.matching import CanonicalRegistry

AS_OF = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=2)


def _participant(slug: str) -> Participant:
    return Participant(
        id=ParticipantId(f"participant:{slug}"),
        sport=Sport.FOOTBALL,
        name=slug.replace("-", " ").title(),
        kind=ParticipantKind.TEAM,
    )


def _winner_registry() -> tuple[CanonicalRegistry, Event, Market, tuple[Selection, ...]]:
    home = _participant("home")
    away = _participant("away")
    competition = Competition(
        id=CompetitionId("competition:test"),
        sport=Sport.FOOTBALL,
        name="Test League",
    )
    event = Event(
        id=EventId("event:test"),
        sport=Sport.FOOTBALL,
        competition=competition,
        participants=(home, away),
        scheduled_start=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
    )
    market = Market(
        id=MarketId("market:test:1x2"),
        event_id=event.id,
        kind=MarketKind.MATCH_WINNER_3_WAY,
        period=MarketPeriod.REGULATION,
    )
    selections = (
        Selection(
            id=SelectionId("selection:test:home"),
            market_id=market.id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=home.id,
        ),
        Selection(
            id=SelectionId("selection:test:draw"),
            market_id=market.id,
            kind=SelectionKind.DRAW,
        ),
        Selection(
            id=SelectionId("selection:test:away"),
            market_id=market.id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=away.id,
        ),
    )
    return (
        CanonicalRegistry(
            competitions=(competition,),
            participants=(home, away),
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
    provider: str,
    event_id: EventId,
    market_id: MarketId,
    selection_id: SelectionId,
    price: str,
    seconds_old: int = 15,
    status: QuoteStatus = QuoteStatus.ACTIVE,
    quote_suffix: str | None = None,
) -> OddsQuote:
    suffix = quote_suffix or f"{provider}:{selection_id.value}:{price}:{seconds_old}:{status.value}"
    return OddsQuote(
        id=QuoteId(f"quote:{suffix}"),
        provider_id=ProviderId(f"provider:{provider}"),
        event_id=event_id,
        market_id=market_id,
        selection_id=selection_id,
        decimal_price=Decimal(price),
        source_event_id=f"{provider}:event",
        source_market_id=f"{provider}:market",
        source_selection_id=f"{provider}:{selection_id.value}",
        source_timestamp=AS_OF - timedelta(seconds=seconds_old),
        ingested_at=AS_OF,
        status=status,
        trace_id=f"trace:{suffix}",
    )


def _complete_quotes(
    event: Event,
    market: Market,
    selections: tuple[Selection, ...],
) -> tuple[OddsQuote, ...]:
    return tuple(
        _quote(
            provider="alpha",
            event_id=event.id,
            market_id=market.id,
            selection_id=selection.id,
            price=price,
        )
        for selection, price in zip(selections, ("2.80", "3.50", "3.00"), strict=True)
    )


def _selected_quote(result_quotes: tuple[OddsQuote, ...], selection_id: SelectionId) -> OddsQuote:
    return next(quote for quote in result_quotes if quote.selection_id == selection_id)


def test_selects_best_valid_price_per_outcome_with_provider_attribution() -> None:
    registry, event, market, selections = _winner_registry()
    alpha = _complete_quotes(event, market, selections)
    beta = tuple(
        _quote(
            provider="beta",
            event_id=event.id,
            market_id=market.id,
            selection_id=selection.id,
            price=price,
        )
        for selection, price in zip(selections, ("2.90", "3.40", "3.20"), strict=True)
    )

    result = build_market_books(
        (*alpha, *beta),
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    assert len(result.books) == 1
    book = result.books[0]
    selected = {outcome.selection.id: outcome.quote for outcome in book.outcomes}
    assert selected[selections[0].id].provider_id == ProviderId("provider:beta")
    assert selected[selections[1].id].provider_id == ProviderId("provider:alpha")
    assert selected[selections[2].id].provider_id == ProviderId("provider:beta")
    assert tuple(outcome.selection.id for outcome in book.outcomes) == tuple(
        sorted((selection.id for selection in selections), key=lambda value: value.value)
    )


def test_stale_high_price_is_removed_before_best_price_selection() -> None:
    registry, event, market, selections = _winner_registry()
    quotes = (
        *_complete_quotes(event, market, selections),
        _quote(
            provider="stale",
            event_id=event.id,
            market_id=market.id,
            selection_id=selections[0].id,
            price="9.00",
            seconds_old=600,
        ),
    )

    result = build_market_books(
        quotes,
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    selected = _selected_quote(result.books[0].quotes, selections[0].id)
    assert selected.decimal_price == Decimal("2.80")
    assert MarketBookDiagnosticCode.STALE_QUOTE in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_inactive_quote_is_removed_before_best_price_selection() -> None:
    registry, event, market, selections = _winner_registry()
    quotes = (
        *_complete_quotes(event, market, selections),
        _quote(
            provider="suspended",
            event_id=event.id,
            market_id=market.id,
            selection_id=selections[1].id,
            price="9.00",
            status=QuoteStatus.SUSPENDED,
        ),
    )

    result = build_market_books(
        quotes,
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    assert all(
        outcome.quote.provider_id != ProviderId("provider:suspended")
        for outcome in result.books[0].outcomes
    )
    assert MarketBookDiagnosticCode.INACTIVE_QUOTE in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_provider_exclusion_forces_best_price_fallback() -> None:
    registry, event, market, selections = _winner_registry()
    alpha = _complete_quotes(event, market, selections)
    beta_best = _quote(
        provider="beta",
        event_id=event.id,
        market_id=market.id,
        selection_id=selections[0].id,
        price="9.00",
    )

    result = build_market_books(
        (*alpha, beta_best),
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
        provider_policy=ProviderBookPolicy(
            excluded_provider_ids=(ProviderId("provider:beta"),),
        ),
    )

    selected = _selected_quote(result.books[0].quotes, selections[0].id)
    assert selected.provider_id == ProviderId("provider:alpha")
    assert MarketBookDiagnosticCode.PROVIDER_FILTERED in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_provider_inclusion_can_make_market_incomplete() -> None:
    registry, event, market, selections = _winner_registry()
    quotes = (
        _quote(
            provider="alpha",
            event_id=event.id,
            market_id=market.id,
            selection_id=selections[0].id,
            price="2.80",
        ),
        _quote(
            provider="beta",
            event_id=event.id,
            market_id=market.id,
            selection_id=selections[1].id,
            price="3.50",
        ),
        _quote(
            provider="beta",
            event_id=event.id,
            market_id=market.id,
            selection_id=selections[2].id,
            price="3.00",
        ),
    )

    result = build_market_books(
        quotes,
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
        provider_policy=ProviderBookPolicy(
            included_provider_ids=(ProviderId("provider:alpha"),),
        ),
    )

    assert result.books == ()
    assert MarketBookDiagnosticCode.INCOMPLETE_MARKET in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_incomplete_market_is_rejected() -> None:
    registry, event, market, selections = _winner_registry()
    quotes = _complete_quotes(event, market, selections)[:2]

    result = build_market_books(
        quotes,
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    assert result.books == ()
    incomplete = next(
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.code is MarketBookDiagnosticCode.INCOMPLETE_MARKET
    )
    assert selections[2].id.value in incomplete.detail


def test_incompatible_total_lines_are_never_combined() -> None:
    home = _participant("home")
    away = _participant("away")
    competition = Competition(
        id=CompetitionId("competition:totals"),
        sport=Sport.FOOTBALL,
        name="Totals League",
    )
    event = Event(
        id=EventId("event:totals"),
        sport=Sport.FOOTBALL,
        competition=competition,
        participants=(home, away),
        scheduled_start=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
    )
    market_25 = Market(
        id=MarketId("market:total:2.5"),
        event_id=event.id,
        kind=MarketKind.TOTAL_POINTS,
        line=Decimal("2.5"),
    )
    market_35 = Market(
        id=MarketId("market:total:3.5"),
        event_id=event.id,
        kind=MarketKind.TOTAL_POINTS,
        line=Decimal("3.5"),
    )
    over_25 = Selection(
        id=SelectionId("selection:over:2.5"),
        market_id=market_25.id,
        kind=SelectionKind.OVER,
    )
    under_25 = Selection(
        id=SelectionId("selection:under:2.5"),
        market_id=market_25.id,
        kind=SelectionKind.UNDER,
    )
    over_35 = Selection(
        id=SelectionId("selection:over:3.5"),
        market_id=market_35.id,
        kind=SelectionKind.OVER,
    )
    under_35 = Selection(
        id=SelectionId("selection:under:3.5"),
        market_id=market_35.id,
        kind=SelectionKind.UNDER,
    )
    registry = CanonicalRegistry(
        competitions=(competition,),
        participants=(home, away),
        events=(event,),
        markets=(market_25, market_35),
        selections=(over_25, under_25, over_35, under_35),
    )
    quotes = (
        _quote(
            provider="alpha",
            event_id=event.id,
            market_id=market_25.id,
            selection_id=over_25.id,
            price="2.20",
        ),
        _quote(
            provider="beta",
            event_id=event.id,
            market_id=market_35.id,
            selection_id=under_35.id,
            price="2.20",
        ),
    )

    result = build_market_books(
        quotes,
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    assert result.books == ()
    incomplete_ids = {
        diagnostic.market_id
        for diagnostic in result.diagnostics
        if diagnostic.code is MarketBookDiagnosticCode.INCOMPLETE_MARKET
    }
    assert incomplete_ids == {market_25.id, market_35.id}


def test_equal_prices_use_freshness_then_stable_identity_independent_of_input_order() -> None:
    registry, event, market, selections = _winner_registry()
    target = selections[0].id
    base = tuple(
        quote
        for quote in _complete_quotes(event, market, selections)
        if quote.selection_id != target
    )
    older = _quote(
        provider="alpha",
        event_id=event.id,
        market_id=market.id,
        selection_id=target,
        price="3.00",
        seconds_old=30,
    )
    fresher_beta = _quote(
        provider="beta",
        event_id=event.id,
        market_id=market.id,
        selection_id=target,
        price="3.00",
        seconds_old=5,
    )
    fresher_alpha = _quote(
        provider="alpha",
        event_id=event.id,
        market_id=market.id,
        selection_id=target,
        price="3.00",
        seconds_old=5,
        quote_suffix="alpha:fresh-tie",
    )

    first = build_market_books(
        (*base, older, fresher_beta, fresher_alpha),
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )
    second = build_market_books(
        (fresher_alpha, fresher_beta, older, *reversed(base)),
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    assert _selected_quote(first.books[0].quotes, target) == fresher_alpha
    assert _selected_quote(second.books[0].quotes, target) == fresher_alpha


def test_future_quote_is_rejected() -> None:
    registry, event, market, selections = _winner_registry()
    future = OddsQuote(
        id=QuoteId("quote:future"),
        provider_id=ProviderId("provider:future"),
        event_id=event.id,
        market_id=market.id,
        selection_id=selections[0].id,
        decimal_price=Decimal("9.00"),
        source_event_id="future:event",
        source_market_id="future:market",
        source_selection_id="future:selection",
        source_timestamp=AS_OF + timedelta(seconds=1),
        ingested_at=AS_OF,
        status=QuoteStatus.ACTIVE,
        trace_id="trace:future",
    )

    result = build_market_books(
        (*_complete_quotes(event, market, selections), future),
        registry=registry,
        as_of=AS_OF,
        freshness_window=WINDOW,
    )

    assert MarketBookDiagnosticCode.FUTURE_QUOTE in {
        diagnostic.code for diagnostic in result.diagnostics
    }
    assert future not in result.books[0].quotes


def test_quote_with_selection_from_another_market_fails_closed() -> None:
    registry, event, market, selections = _winner_registry()
    other_market = Market(
        id=MarketId("market:test:other"),
        event_id=event.id,
        kind=MarketKind.MATCH_WINNER_2_WAY,
    )
    other_selection = Selection(
        id=SelectionId("selection:test:other"),
        market_id=other_market.id,
        kind=SelectionKind.PARTICIPANT,
        participant_id=event.participants[0].id,
    )
    expanded = CanonicalRegistry(
        competitions=registry.competitions,
        participants=registry.participants,
        events=registry.events,
        markets=(*registry.markets, other_market),
        selections=(*registry.selections, other_selection),
    )
    invalid = _quote(
        provider="bad",
        event_id=event.id,
        market_id=market.id,
        selection_id=other_selection.id,
        price="9.00",
    )

    result = build_market_books(
        (*_complete_quotes(event, market, selections), invalid),
        registry=expanded,
        as_of=AS_OF,
        freshness_window=WINDOW,
        market_ids=(market.id,),
    )

    assert MarketBookDiagnosticCode.QUOTE_SELECTION_MISMATCH in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_provider_policy_rejects_overlap() -> None:
    provider_id = ProviderId("provider:alpha")
    with pytest.raises(ValueError, match="both included and excluded"):
        ProviderBookPolicy(
            included_provider_ids=(provider_id,),
            excluded_provider_ids=(provider_id,),
        )
