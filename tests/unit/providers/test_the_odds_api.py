"""Unit tests for the first real odds-data provider adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from arbiscan.domain import ProviderId, Sport
from arbiscan.observability.provider import InMemoryProviderTelemetry, ProviderTelemetryOutcome
from arbiscan.providers import ProviderError, ProviderErrorKind, ProviderHealthState
from arbiscan.providers.http import HttpResponse
from arbiscan.providers.the_odds_api import TheOddsApiConfig, TheOddsApiProvider
from tests.support.the_odds_api import FixtureHttpTransport

NOW = datetime(2026, 9, 20, 11, 5, tzinfo=UTC)
FIXTURE_KEY = "fixture"


def _build(
    *,
    transport: FixtureHttpTransport | None = None,
) -> tuple[TheOddsApiProvider, FixtureHttpTransport, InMemoryProviderTelemetry]:
    fixture_transport = transport or FixtureHttpTransport()
    telemetry = InMemoryProviderTelemetry()
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY),
        transport=fixture_transport,
        telemetry=telemetry,
        clock=lambda: NOW,
    )
    return provider, fixture_transport, telemetry


def test_config_repr_hides_credential() -> None:
    config = TheOddsApiConfig(api_key=FIXTURE_KEY)

    assert FIXTURE_KEY not in repr(config)


def test_discovery_maps_only_supported_canonical_sports() -> None:
    provider, _transport, _telemetry = _build()

    sports = asyncio.run(provider.supported_sports())
    football = asyncio.run(provider.discover_competitions(Sport.FOOTBALL))
    tennis = asyncio.run(provider.discover_competitions(Sport.TENNIS))

    assert sports == (Sport.FOOTBALL, Sport.TENNIS)
    assert tuple(value.external_id for value in football) == ("soccer_epl",)
    assert tuple(value.external_id for value in tennis) == ("tennis_atp_us_open",)


def test_event_and_odds_preserve_bookmaker_origin_and_freshness() -> None:
    provider, transport, telemetry = _build()

    events = asyncio.run(provider.discover_events("soccer_epl"))
    assert len(events) == 1
    event = events[0]
    assert event.external_id == "epl-arsenal-chelsea-20260920"
    assert tuple(value.name for value in event.participants) == ("Arsenal", "Chelsea")

    snapshot = asyncio.run(provider.fetch_odds(event.external_id))
    assert snapshot is not None
    assert snapshot.provider_id == ProviderId("provider:the-odds-api")
    assert len(snapshot.markets) == 2
    assert {
        market.price_provider.id for market in snapshot.markets if market.price_provider is not None
    } == {
        ProviderId("bookmaker:the-odds-api:pinnacle"),
        ProviderId("bookmaker:the-odds-api:unibet_eu"),
    }
    assert {market.source_timestamp for market in snapshot.markets} == {
        datetime(2026, 9, 20, 11, 4, tzinfo=UTC),
        datetime(2026, 9, 20, 11, 4, 30, tzinfo=UTC),
    }

    rate_limit = asyncio.run(provider.rate_limit())
    assert rate_limit is not None
    assert rate_limit.limit == 500
    assert rate_limit.remaining == 487

    request = transport.requests[-1]
    assert request.query["apiKey"] == FIXTURE_KEY
    assert request.query["regions"] == "eu"
    assert request.query["markets"] == "h2h"
    assert request.query["oddsFormat"] == "decimal"
    assert FIXTURE_KEY not in repr(telemetry.events)
    assert telemetry.events[-1].outcome is ProviderTelemetryOutcome.SUCCESS
    assert telemetry.events[-1].request_cost == 1


def test_rate_limit_response_becomes_retryable_structured_error() -> None:
    provider, _transport, telemetry = _build(
        transport=FixtureHttpTransport(status_code=429, retry_after="7")
    )

    try:
        asyncio.run(provider.supported_sports())
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.RATE_LIMITED
        assert error.retryable
        assert error.retry_after == timedelta(seconds=7)
        assert FIXTURE_KEY not in str(error)
    else:
        raise AssertionError("expected rate-limit ProviderError")

    rate_limit = asyncio.run(provider.rate_limit())
    assert rate_limit is not None
    assert rate_limit.retry_after == timedelta(seconds=7)
    assert telemetry.events[-1].outcome is ProviderTelemetryOutcome.FAILURE
    assert telemetry.events[-1].error_kind == ProviderErrorKind.RATE_LIMITED.value


def test_health_degrades_without_leaking_credential() -> None:
    provider, _transport, _telemetry = _build(transport=FixtureHttpTransport(status_code=401))

    health = asyncio.run(provider.health())

    assert health.state is ProviderHealthState.UNAVAILABLE
    assert health.detail is not None
    assert "authentication" in health.detail
    assert FIXTURE_KEY not in health.detail


def test_malformed_payload_fails_closed() -> None:
    class MalformedTransport:
        async def get(
            self,
            *,
            url: str,
            query: Mapping[str, str],
            timeout_seconds: float,
        ) -> HttpResponse:
            _ = (url, query, timeout_seconds)
            return HttpResponse(status_code=200, headers={}, body=b'{"unexpected":true}')

    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY),
        transport=MalformedTransport(),
        clock=lambda: NOW,
    )

    try:
        asyncio.run(provider.supported_sports())
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert not error.retryable
    else:
        raise AssertionError("expected malformed-response ProviderError")
