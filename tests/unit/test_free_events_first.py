"""No paid OddsPapi discovery until free The Odds API event listing passes."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import redirect_stdout
from io import StringIO

from scripts.discover_live_overlap import run_discovery

from arbiscan.providers import HttpResponse
from tests.support.oddspapi import FixtureHttpTransport as OddsPapiFixture
from tests.support.the_odds_api import FixtureHttpTransport as OddsApiFixture


class _EventsStatusTransport:
    def __init__(self, event_status: int) -> None:
        self.event_status = event_status
        self.fixture = OddsApiFixture()
        self.events_attempted = 0

    async def get(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        if url.endswith("/sports/soccer_epl/events"):
            self.events_attempted += 1
            return HttpResponse(
                status_code=self.event_status,
                headers={"x-requests-remaining": "500", "x-requests-used": "0"},
                body=b'{"sensitive_data":"never-print-this-upstream-body"}',
            )
        return await self.fixture.get(url=url, query=query, timeout_seconds=timeout_seconds)


def _run_test(
    *,
    odds_status: int | None,
    odds_only: bool = False,
) -> tuple[int, str, OddsPapiFixture, _EventsStatusTransport | OddsApiFixture]:
    papi = OddsPapiFixture()
    odds: _EventsStatusTransport | OddsApiFixture = (
        OddsApiFixture() if odds_status is None else _EventsStatusTransport(odds_status)
    )
    output = StringIO()
    with redirect_stdout(output):
        status = asyncio.run(
            run_discovery(
                "fake-odds-key",
                "fake-papi-key",
                odds_only=odds_only,
                odds_upstream=odds,
                papi_upstream=papi,
            )
        )
    return status, output.getvalue(), papi, odds


def test_http_404_identifies_odds_api_without_billable_papi_calls() -> None:
    result, output, papi, odds = _run_test(odds_status=404)
    assert result == 1
    assert "The Odds API discover_events (upstream; HTTP 404)" in output
    assert "OddsPapi billable calls attempted = 0/3" in output
    assert "never-print-this-upstream-body" not in output
    assert "fake-odds-key" not in output
    assert "fake-papi-key" not in output
    assert isinstance(odds, _EventsStatusTransport)
    assert odds.events_attempted == 1
    assert not papi.requests


def test_http_503_is_reported_and_does_not_retry_or_spend_papi() -> None:
    result, output, papi, odds = _run_test(odds_status=503)
    assert result == 1
    assert "The Odds API discover_events (upstream; HTTP 503)" in output
    assert isinstance(odds, _EventsStatusTransport)
    assert odds.events_attempted == 1
    assert not papi.requests


def test_odds_only_success_never_contacts_papi() -> None:
    result, output, papi, odds = _run_test(odds_status=None, odds_only=True)
    assert result == 0
    assert "The Odds API free event discovery passed" in output
    assert "OddsPapi billable calls attempted = 0/3" in output
    assert "OddsPapi discovery skipped" in output
    assert not papi.requests
    assert isinstance(odds, OddsApiFixture)
    assert any(request.url.endswith("/sports/soccer_epl/events") for request in odds.requests)
