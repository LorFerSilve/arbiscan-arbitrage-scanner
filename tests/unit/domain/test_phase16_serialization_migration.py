"""Compatibility tests for the Phase-16 canonical schema migration."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.domain import (
    SCHEMA_VERSION,
    EventId,
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    OddsQuote,
    ProviderId,
    QuoteId,
    QuoteStatus,
    SelectionId,
    dumps,
    loads,
)


def _quote() -> OddsQuote:
    return OddsQuote(
        id=QuoteId("quote:phase16"),
        provider_id=ProviderId("bookmaker:a"),
        transport_provider_id=ProviderId("transport:a"),
        event_id=EventId("event:1"),
        market_id=MarketId("market:1"),
        selection_id=SelectionId("selection:1"),
        decimal_price=Decimal("2.10"),
        source_event_id="source-event",
        source_market_id="source-market",
        source_selection_id="source-selection",
        source_timestamp=datetime(2026, 9, 17, 1, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 9, 17, 1, 0, 1, tzinfo=UTC),
        status=QuoteStatus.ACTIVE,
        trace_id="trace:phase16",
    )


def test_schema_version_tracks_current_phase17_market_identity() -> None:
    assert SCHEMA_VERSION == 3
    payload = json.loads(dumps(_quote()))
    assert payload["schema_version"] == 3
    assert payload["payload"]["transport_provider_id"]["value"] == "transport:a"


def test_schema_v1_quote_migrates_transport_to_legacy_price_provider() -> None:
    payload = json.loads(dumps(_quote()))
    payload["schema_version"] = 1
    del payload["payload"]["transport_provider_id"]

    restored = loads(json.dumps(payload), OddsQuote)

    assert restored.provider_id == ProviderId("bookmaker:a")
    assert restored.transport_provider_id == ProviderId("bookmaker:a")


def test_current_schema_round_trip_preserves_distinct_transport_and_price_provider() -> None:
    quote = _quote()
    restored = loads(dumps(quote), OddsQuote)

    assert restored == quote
    assert restored.provider_id == ProviderId("bookmaker:a")
    assert restored.transport_provider_id == ProviderId("transport:a")


def test_schema_v2_market_migrates_new_optional_phase17_identity_fields() -> None:
    market = Market(
        id=MarketId("market:legacy-v2"),
        event_id=EventId("event:legacy-v2"),
        kind=MarketKind.MATCH_WINNER_2_WAY,
        period=MarketPeriod.FULL_EVENT,
    )
    payload = json.loads(dumps(market))
    payload["schema_version"] = 2
    del payload["payload"]["set_index"]
    del payload["payload"]["subject_participant_id"]

    restored = loads(json.dumps(payload), Market)

    assert restored == market
    assert restored.set_index is None
    assert restored.subject_participant_id is None
