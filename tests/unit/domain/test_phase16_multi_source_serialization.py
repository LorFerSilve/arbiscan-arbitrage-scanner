"""Phase 16.2 serialization compatibility tests for source provenance."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from arbiscan.domain import (
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    EventId,
    MarketId,
    SelectionId,
    dumps,
    loads,
)
from arbiscan.domain.serialization import SCHEMA_VERSION

PRICE_PROVIDER = ProviderId("bookmaker:shared")
SOURCE_PROVIDER = ProviderId("provider:the-odds-api")


def _quote() -> OddsQuote:
    return OddsQuote(
        id=QuoteId("quote:phase16-serialization"),
        provider_id=PRICE_PROVIDER,
        source_provider_id=SOURCE_PROVIDER,
        event_id=EventId("event:phase16"),
        market_id=MarketId("market:phase16"),
        selection_id=SelectionId("selection:phase16"),
        decimal_price=Decimal("2.15"),
        source_event_id="external-event",
        source_market_id="external-market",
        source_selection_id="external-selection",
        ingested_at=datetime(2026, 9, 17, 0, 0, tzinfo=UTC),
        status=QuoteStatus.ACTIVE,
        trace_id="trace:phase16",
        raw_source_reference=(
            "source://provider:the-odds-api/bookmaker:shared/"
            "external-event/external-market/external-selection"
        ),
    )


def test_schema_v2_round_trip_preserves_price_and_source_provider_identity() -> None:
    quote = _quote()

    restored = loads(dumps(quote), OddsQuote)

    assert SCHEMA_VERSION == 2
    assert restored == quote
    assert restored.provider_id == PRICE_PROVIDER
    assert restored.price_provider_id == PRICE_PROVIDER
    assert restored.source_provider_id == SOURCE_PROVIDER


def test_schema_v1_quote_payload_migrates_transport_identity_from_raw_reference() -> None:
    encoded = cast(dict[str, Any], json.loads(dumps(_quote())))
    encoded["schema_version"] = 1
    payload = cast(dict[str, Any], encoded["payload"])
    payload.pop("source_provider_id")

    restored = loads(json.dumps(encoded), OddsQuote)

    assert restored.provider_id == PRICE_PROVIDER
    assert restored.source_provider_id == SOURCE_PROVIDER
