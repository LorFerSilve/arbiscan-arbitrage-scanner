"""Phase 16.2 tests for collision-free source-observation identifiers."""

from datetime import UTC, datetime

from arbiscan.domain import EventId, MarketId, ProviderId, SelectionId
from arbiscan.normalization.strict import _quote_id

EFFECTIVE_AT = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)


def _id(source_provider_id: ProviderId) -> object:
    return _quote_id(
        source_provider_id=source_provider_id,
        price_provider_id=ProviderId("bookmaker:shared"),
        event_id=EventId("event:shared"),
        market_id=MarketId("market:shared"),
        selection_id=SelectionId("selection:shared"),
        source_event_id="external-event",
        source_market_id="external-market",
        source_selection_id="external-selection",
        effective_timestamp=EFFECTIVE_AT,
    )


def test_quote_observation_id_changes_with_transport_source() -> None:
    the_odds_id = _id(ProviderId("provider:the-odds-api"))
    oddspapi_id = _id(ProviderId("provider:oddspapi"))

    assert the_odds_id != oddspapi_id
    assert the_odds_id == _id(ProviderId("provider:the-odds-api"))
