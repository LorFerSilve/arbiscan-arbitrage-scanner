"""Historical batches preserve independent transport observations."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.backtesting import HistoricalQuoteCorpus
from arbiscan.domain import (
    EventId,
    MarketId,
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
)

OBSERVED_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)
PRICE_ORIGIN = ProviderId("provider:bookmaker")
TRANSPORT_A = ProviderId("provider:transport-a")
TRANSPORT_B = ProviderId("provider:transport-b")


def _quote(transport: ProviderId, *, price: str = "2.10") -> OddsQuote:
    return OddsQuote(
        id=QuoteId(f"quote:{transport.value}"),
        provider_id=PRICE_ORIGIN,
        transport_provider_id=transport,
        event_id=EventId("event:fixture"),
        market_id=MarketId("market:winner"),
        selection_id=SelectionId("selection:home"),
        decimal_price=Decimal(price),
        source_event_id="source:event:fixture",
        source_market_id="source:market:winner",
        source_selection_id="source:selection:home",
        source_timestamp=OBSERVED_AT,
        ingested_at=OBSERVED_AT,
        status=QuoteStatus.ACTIVE,
        trace_id=f"trace:{transport.value}",
    )


def test_parallel_transports_are_preserved_with_stable_corpus_digest() -> None:
    first = _quote(TRANSPORT_A)
    second = _quote(TRANSPORT_B)

    forward = HistoricalQuoteCorpus.from_quotes((first, second))
    reversed_input = HistoricalQuoteCorpus.from_quotes((second, first))

    assert forward.batches[0].quotes == (first, second)
    assert reversed_input.batches[0].quotes == (first, second)
    assert forward.digest == reversed_input.digest


def test_conflicting_parallel_transports_remain_available_as_evidence() -> None:
    first = _quote(TRANSPORT_A)
    conflicting = _quote(TRANSPORT_B, price="2.20")

    corpus = HistoricalQuoteCorpus.from_quotes((first, conflicting))

    assert corpus.batches[0].quotes == (first, conflicting)


def test_same_transport_cannot_update_one_observation_twice_in_a_batch() -> None:
    first = _quote(TRANSPORT_A)
    duplicate = replace(first, id=QuoteId("quote:duplicate"))

    try:
        HistoricalQuoteCorpus.from_quotes((first, duplicate))
    except ValueError as error:
        assert "SourceObservationKey" in str(error)
    else:
        raise AssertionError("duplicate transport observation must fail closed")
