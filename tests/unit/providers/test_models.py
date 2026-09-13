"""Validation tests for provider-neutral source records and metadata."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from arbiscan.domain import ProviderId, Sport
from arbiscan.providers import (
    OddsSnapshot,
    ProviderCapabilities,
    ProviderCapability,
    ProviderContractError,
    RateLimitSnapshot,
    SourceEvent,
    SourceMarket,
    SourceOddsFormat,
    SourceParticipant,
    SourceSelectionQuote,
)

NOW = datetime(2026, 9, 13, 10, 0, tzinfo=UTC)


def expect_contract_error(action: Callable[[], object], *, contains: str) -> None:
    try:
        action()
    except ProviderContractError as exc:
        if contains not in str(exc):
            raise AssertionError(f"expected {contains!r} in {exc!r}") from exc
        return
    raise AssertionError("expected ProviderContractError")


def test_capabilities_are_immutable_and_explicit() -> None:
    capabilities = ProviderCapabilities(
        frozenset(
            {
                ProviderCapability.EVENT_DISCOVERY,
                ProviderCapability.ODDS_SNAPSHOTS,
            }
        )
    )
    assert capabilities.supports(ProviderCapability.EVENT_DISCOVERY)
    assert not capabilities.supports(ProviderCapability.ODDS_STREAMING)


def test_source_event_rejects_naive_timestamp() -> None:
    participant = SourceParticipant(external_id="team:a", name="A")
    expect_contract_error(
        lambda: SourceEvent(
            external_id="event:1",
            sport=Sport.FOOTBALL,
            competition_external_id="competition:1",
            participants=(participant,),
            scheduled_start=datetime(2026, 9, 20, 16, 0),
        ),
        contains="timezone-aware",
    )


def test_source_market_rejects_duplicate_selection_ids() -> None:
    selection = SourceSelectionQuote(
        external_selection_id="selection:1",
        label="Home",
        price="2.00",
        odds_format=SourceOddsFormat.DECIMAL,
    )
    expect_contract_error(
        lambda: SourceMarket(
            external_event_id="event:1",
            external_market_id="market:1",
            label="Winner",
            selections=(selection, selection),
        ),
        contains="unique",
    )


def test_snapshot_rejects_market_for_another_event() -> None:
    selection = SourceSelectionQuote(
        external_selection_id="selection:1",
        label="Home",
        price="2.00",
        odds_format=SourceOddsFormat.DECIMAL,
    )
    market = SourceMarket(
        external_event_id="event:other",
        external_market_id="market:1",
        label="Winner",
        selections=(selection,),
    )
    expect_contract_error(
        lambda: OddsSnapshot(
            provider_id=ProviderId("provider:1"),
            external_event_id="event:1",
            markets=(market,),
            ingested_at=NOW,
        ),
        contains="snapshot event",
    )


def test_rate_limit_metadata_is_consistent() -> None:
    snapshot = RateLimitSnapshot(
        provider_id=ProviderId("provider:1"),
        observed_at=NOW,
        limit=100,
        remaining=40,
        resets_at=NOW + timedelta(minutes=1),
        retry_after=timedelta(seconds=2),
    )
    assert snapshot.remaining == 40

    expect_contract_error(
        lambda: RateLimitSnapshot(
            provider_id=ProviderId("provider:1"),
            observed_at=NOW,
            limit=10,
            remaining=11,
        ),
        contains="cannot exceed",
    )
