"""Compatibility tests for Phase-16 canonical serialization migration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
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
    loads,
)


def _quote() -> OddsQuote:
    provider_id = ProviderId("bookmaker:legacy")
    return OddsQuote(
        id=QuoteId("quote:legacy"),
        provider_id=provider_id,
        transport_provider_id=provider_id,
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


def test_schema_v1_quote_migrates_transport_identity_from_provider() -> None:
    quote = _quote()
    encoded = cast(dict[str, object], json.loads(dumps(quote)))
    encoded["schema_version"] = 1
    payload = cast(dict[str, object], encoded["payload"])
    del payload["transport_provider_id"]
    legacy = json.dumps(encoded, sort_keys=True, separators=(",", ":"))

    restored = loads(legacy, OddsQuote)

    assert restored == quote
    assert restored.transport_provider_id == quote.provider_id


def test_current_schema_round_trip_keeps_distinct_transport_provider() -> None:
    quote = _quote()
    distinct = OddsQuote(
        id=quote.id,
        provider_id=quote.provider_id,
        transport_provider_id=ProviderId("provider:transport-a"),
        event_id=quote.event_id,
        market_id=quote.market_id,
        selection_id=quote.selection_id,
        decimal_price=quote.decimal_price,
        source_event_id=quote.source_event_id,
        source_market_id=quote.source_market_id,
        source_selection_id=quote.source_selection_id,
        source_timestamp=quote.source_timestamp,
        ingested_at=quote.ingested_at,
        status=quote.status,
        trace_id=quote.trace_id,
    )

    restored = loads(dumps(distinct), OddsQuote)

    assert restored == distinct
    assert restored.transport_provider_id == ProviderId("provider:transport-a")
