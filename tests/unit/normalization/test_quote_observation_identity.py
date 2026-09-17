"""Regression tests for Phase-16 source-observation quote identity."""

from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.domain import EventId, MarketId, ProviderId, SelectionId
from arbiscan.normalization.strict import _quote_id

AS_OF = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def _id(*, transport: str, price: str = "2.10") -> str:
    return _quote_id(
        ProviderId(transport),
        ProviderId("bookmaker:pinnacle"),
        EventId("event:test"),
        MarketId("market:test"),
        SelectionId("selection:test"),
        "source-event",
        "source-market",
        "source-selection",
        AS_OF,
        Decimal(price),
    ).value


def test_same_bookmaker_observation_from_two_transports_cannot_collide() -> None:
    assert _id(transport="provider:source-a") != _id(transport="provider:source-b")


def test_same_source_timestamp_price_correction_cannot_reuse_observation_id() -> None:
    assert _id(transport="provider:source-a", price="2.10") != _id(
        transport="provider:source-a", price="2.20"
    )


def test_observation_identity_is_deterministic() -> None:
    assert _id(transport="provider:source-a") == _id(transport="provider:source-a")
