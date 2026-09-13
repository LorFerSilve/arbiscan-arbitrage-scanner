"""Regression tests for Phase 6 provider-review findings."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime

from arbiscan.domain import Sport
from arbiscan.observability.provider import InMemoryProviderTelemetry, ProviderTelemetryOutcome
from arbiscan.providers import ProviderError, ProviderErrorKind
from arbiscan.providers.http import HttpResponse
from arbiscan.providers.the_odds_api import TheOddsApiConfig, TheOddsApiProvider
from tests.support.the_odds_api import FixtureHttpTransport

NOW = datetime(2026, 9, 20, 11, 5, tzinfo=UTC)


class StaticJsonTransport:
    """Return one deterministic JSON document for every request."""

    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    async def get(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        _ = (url, query, timeout_seconds)
        return HttpResponse(status_code=200, headers={}, body=self._body)


class InvalidEventsTransport:
    """Return valid sport discovery followed by a malformed events payload."""

    def __init__(self) -> None:
        self._calls = 0

    async def get(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        _ = (url, query, timeout_seconds)
        self._calls += 1
        if self._calls == 1:
            payload: object = [
                {
                    "key": "soccer_epl",
                    "group": "Soccer",
                    "title": "Premier League",
                    "active": True,
                }
            ]
        else:
            payload = {"unexpected": True}
        return HttpResponse(
            status_code=200,
            headers={},
            body=json.dumps(payload).encode("utf-8"),
        )


def test_source_model_validation_is_translated_to_malformed_response() -> None:
    telemetry = InMemoryProviderTelemetry()
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture"),
        transport=StaticJsonTransport(
            [
                {
                    "key": "soccer_epl",
                    "group": "Soccer",
                    "title": "x" * 513,
                    "active": True,
                }
            ]
        ),
        telemetry=telemetry,
        clock=lambda: NOW,
    )

    try:
        asyncio.run(provider.discover_competitions(Sport.FOOTBALL))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert not error.retryable
    else:
        raise AssertionError("expected malformed-response ProviderError")

    assert len(telemetry.events) == 1
    assert telemetry.events[0].outcome is ProviderTelemetryOutcome.FAILURE
    assert telemetry.events[0].error_kind == ProviderErrorKind.MALFORMED_RESPONSE.value


def test_failed_event_validation_does_not_emit_prevalidation_success() -> None:
    telemetry = InMemoryProviderTelemetry()
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture"),
        transport=InvalidEventsTransport(),
        telemetry=telemetry,
        clock=lambda: NOW,
    )

    try:
        asyncio.run(provider.discover_events("soccer_epl"))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
    else:
        raise AssertionError("expected malformed-response ProviderError")

    assert len(telemetry.events) == 1
    assert telemetry.events[0].operation == "discover_events"
    assert telemetry.events[0].outcome is ProviderTelemetryOutcome.FAILURE
    assert telemetry.events[0].error_kind == ProviderErrorKind.MALFORMED_RESPONSE.value


def test_successful_event_discovery_emits_one_operation_success() -> None:
    telemetry = InMemoryProviderTelemetry()
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key="fixture"),
        transport=FixtureHttpTransport(),
        telemetry=telemetry,
        clock=lambda: NOW,
    )

    events = asyncio.run(provider.discover_events("soccer_epl"))

    assert len(events) == 1
    operation_events = [event for event in telemetry.events if event.operation == "discover_events"]
    assert len(operation_events) == 1
    assert operation_events[0].outcome is ProviderTelemetryOutcome.SUCCESS
    assert operation_events[0].item_count == 1
