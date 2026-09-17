"""Phase 16.2 regressions for transport provenance and overlap consolidation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
)
from arbiscan.ingestion.multisource import (
    ConsolidationDiagnosticCode,
    SourceObservationKey,
    consolidate_quotes,
)
from arbiscan.normalization.strict import _quote_id

NOW = datetime(2026, 9, 17, 1, 0, tzinfo=UTC)
PRICE_PROVIDER = ProviderId("bookmaker:pinnacle")
TRANSPORT_A = ProviderId("transport:the-odds-api")
TRANSPORT_B = ProviderId("transport:oddspapi")
EVENT = EventId("event:1")
MARKET = MarketId("market:1")
SELECTION = SelectionId("selection:home")


def _quote(
    *,
    transport: ProviderId,
    price: str,
    source_timestamp: datetime = NOW,
    ingested_at: datetime | None = None,
) -> OddsQuote:
    observed_at = ingested_at or source_timestamp + timedelta(seconds=1)
    return OddsQuote(
        id=_quote_id(
            transport,
            PRICE_PROVIDER,
            EVENT,
            MARKET,
            SELECTION,
            source_timestamp,
        ),
        provider_id=PRICE_PROVIDER,
        transport_provider_id=transport,
        event_id=EVENT,
        market_id=MARKET,
        selection_id=SELECTION,
        decimal_price=Decimal(price),
        source_event_id=f"{transport.value}:event",
        source_market_id=f"{transport.value}:market",
        source_selection_id=f"{transport.value}:selection",
        source_timestamp=source_timestamp,
        ingested_at=observed_at,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{transport.value}",
    )


def test_observation_ids_include_transport_source() -> None:
    first = _quote(transport=TRANSPORT_A, price="2.10")
    second = _quote(transport=TRANSPORT_B, price="2.10")

    assert first.id != second.id
    assert SourceObservationKey.from_quote(first) != SourceObservationKey.from_quote(second)
    assert first.provider_id == second.provider_id == PRICE_PROVIDER


def test_newer_transport_observation_wins_without_double_counting_bookmaker() -> None:
    older = _quote(
        transport=TRANSPORT_A,
        price="2.05",
        source_timestamp=NOW - timedelta(seconds=10),
    )
    newer = _quote(transport=TRANSPORT_B, price="2.15")

    result = consolidate_quotes((older, newer))

    assert result.quotes == (newer,)
    assert result.diagnostics == ()
    assert result.equivalent_overlap_count == 0
    assert result.conflict_count == 0


def test_equal_time_equivalent_observations_are_deterministic_and_single_leg() -> None:
    first = _quote(transport=TRANSPORT_A, price="2.10")
    second = _quote(transport=TRANSPORT_B, price="2.10")

    forward = consolidate_quotes((second, first))
    reverse = consolidate_quotes((first, second))

    assert len(forward.quotes) == 1
    assert forward.quotes == reverse.quotes
    assert forward.quotes[0].provider_id == PRICE_PROVIDER
    assert forward.equivalent_overlap_count == 1
    assert forward.conflict_count == 0
    assert forward.diagnostics[0].code is ConsolidationDiagnosticCode.EQUIVALENT_OVERLAP
    assert set(forward.diagnostics[0].transport_provider_ids) == {TRANSPORT_A, TRANSPORT_B}


def test_equal_time_material_conflict_fails_closed() -> None:
    first = _quote(transport=TRANSPORT_A, price="2.10")
    second = _quote(transport=TRANSPORT_B, price="2.20")

    result = consolidate_quotes((first, second))

    assert result.quotes == ()
    assert result.equivalent_overlap_count == 0
    assert result.conflict_count == 1
    assert result.diagnostics[0].code is ConsolidationDiagnosticCode.MATERIAL_CONFLICT
    assert set(result.diagnostics[0].transport_provider_ids) == {TRANSPORT_A, TRANSPORT_B}


def test_legacy_quote_defaults_transport_identity_to_price_provider() -> None:
    quote = OddsQuote(
        id=QuoteId("legacy:quote"),
        provider_id=PRICE_PROVIDER,
        event_id=EVENT,
        market_id=MARKET,
        selection_id=SELECTION,
        decimal_price=Decimal("2.10"),
        source_event_id="event",
        source_market_id="market",
        source_selection_id="selection",
        ingested_at=NOW,
        status=QuoteStatus.ACTIVE,
        trace_id="legacy-trace",
    )

    assert quote.transport_provider_id == PRICE_PROVIDER
