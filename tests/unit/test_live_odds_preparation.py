"""Offline Phase-19 live-odds preflight and route/credit firewall tests."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from arbiscan.providers import HttpResponse, HttpTransportError
from scripts.prepare_live_odds import (
    MetadataOnlyTransport,
    QuoteProbeSource,
    QuoteProbeTransport,
    ReadinessEvidence,
    check_unmetered_quotas,
    main,
    quota_ready,
)
from tests.support.oddspapi import FixtureHttpTransport as PapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as OddsFixtureTransport


class _Recorder:
    def __init__(self, *, fails: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.fails = fails

    async def get(
        self, *, url: str, query: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        self.calls.append((url, dict(query)))
        if self.fails:
            raise HttpTransportError("synthetic failed request")
        return HttpResponse(status_code=200, headers={}, body=b"{}")


def _request(
    transport: MetadataOnlyTransport | QuoteProbeTransport,
    url: str,
    query: Mapping[str, str],
) -> HttpResponse:
    return asyncio.run(transport.get(url=url, query=query, timeout_seconds=1.0))


def _blocked(
    transport: MetadataOnlyTransport | QuoteProbeTransport,
    url: str,
    query: Mapping[str, str],
) -> None:
    try:
        _request(transport, url, query)
    except HttpTransportError:
        return
    raise AssertionError("unapproved provider request was not blocked")


def test_default_offline_plan_does_not_read_keys_or_make_network_calls() -> None:
    output = StringIO()
    with patch("sys.argv", ["prepare_live_odds"]), redirect_stdout(output):
        assert main() == 0
    content = output.getvalue()
    assert "Offline planning: 0 API requests" in content
    assert content.count("Quote authorization BLOCKED:") == 4
    assert "at most 5 billable" in content


def test_readiness_is_blocked_until_every_independent_requirement_is_met() -> None:
    evidence = ReadinessEvidence()
    assert len(evidence.blockers()) == 4
    assert "home-away" in " ".join(evidence.blockers())
    assert len(
        ReadinessEvidence(
            canonical_event_verified=True,
            independent_home_away_verified=True,
        ).blockers()
    ) == 2
    assert (
        ReadinessEvidence(
            canonical_event_verified=True,
            independent_home_away_verified=True,
            bookmaker_regulation_and_void_rules_verified=True,
            provider_data_rights_approved=True,
        ).blockers()
        == ()
    )


def test_one_call_each_unmetered_check_has_no_billable_requests() -> None:
    odds = OddsFixtureTransport()
    papi = PapiFixtureTransport()
    output = StringIO()
    with redirect_stdout(output):
        ok = asyncio.run(
            check_unmetered_quotas(
                "synthetic-odds-key",
                "synthetic-papi-key",
                odds_upstream=odds,
                papi_upstream=papi,
            )
        )
    assert ok
    assert len(odds.requests) == 1
    assert odds.requests[0].url == "https://api.the-odds-api.com/v4/sports"
    assert len(papi.requests) == 1
    assert papi.requests[0].path == "/account"
    assert "Quota reserve PASS" in output.getvalue()
    assert "paid quote requests = 0" in output.getvalue()
    assert "synthetic-" not in output.getvalue()


def test_unmetered_quota_check_fails_closed_on_missing_or_insufficient_allowance() -> None:
    odds = OddsFixtureTransport()
    papi = PapiFixtureTransport(
        body_overrides={
            "/account": (
                b'{"current_subscription_id":"s","subscriptions":['
                b'{"subscription_id":"s","is_active":true,'
                b'"request_limit":10,"request_count":6}]}'
            )
        }
    )
    output = StringIO()
    with redirect_stdout(output):
        assert not asyncio.run(
            check_unmetered_quotas(
                "synthetic-odds-key",
                "synthetic-papi-key",
                odds_upstream=odds,
                papi_upstream=papi,
            )
        )
    assert len(papi.requests) == 1
    assert "Quota reserve BLOCKED" in output.getvalue()
    assert not quota_ready(None, None)


def test_metadata_transport_blocks_odds_and_second_attempt() -> None:
    upstream = _Recorder()
    guard = MetadataOnlyTransport(provider="the_odds_api", upstream=upstream)
    key = {"apiKey": "test-key", "all": "false"}
    _blocked(guard, "https://api.the-odds-api.com/v4/sports/soccer_epl/odds", key)
    _blocked(guard, "https://lookalike.example/v4/sports", key)
    _request(guard, "https://api.the-odds-api.com/v4/sports", key)
    _blocked(guard, "https://api.the-odds-api.com/v4/sports", key)
    assert guard.attempts == 1
    assert len(upstream.calls) == 1

    upstream_papi = _Recorder()
    papi_guard = MetadataOnlyTransport(provider="oddspapi", upstream=upstream_papi)
    _blocked(papi_guard, "https://api.oddspapi.io/v4/markets", {"apiKey": "test-key"})
    _request(papi_guard, "https://api.oddspapi.io/v4/account", {"apiKey": "test-key"})
    assert len(upstream_papi.calls) == 1


def test_one_event_the_odds_api_quote_transport_only_allows_eu_h2h_once() -> None:
    upstream = _Recorder()
    guard = QuoteProbeTransport(
        provider=QuoteProbeSource.THE_ODDS_API,
        external_event_id="safeid123",
        upstream=upstream,
    )
    base = "https://api.the-odds-api.com/v4/sports/soccer_epl/events/"
    q = {
        "apiKey": "test-key",
        "regions": "eu",
        "markets": "h2h",
        "dateFormat": "iso",
        "oddsFormat": "decimal",
        "includeSids": "true",
    }
    _blocked(guard, base + "wrong/odds", q)
    _blocked(guard, base + "safeid123/odds", {**q, "regions": "eu,uk"})
    _blocked(guard, base + "safeid123/odds", {**q, "markets": "h2h,totals"})
    _blocked(guard, base + "safeid123/odds?apiKey=exposed", q)
    assert not upstream.calls
    _request(guard, base + "safeid123/odds", q)
    _blocked(guard, base + "safeid123/odds", q)
    assert len(upstream.calls) == 1
    assert sum(guard.attempts.values()) == 1


def test_one_event_oddspapi_quote_transport_requires_catalog_first_and_caps_two() -> None:
    upstream = _Recorder()
    guard = QuoteProbeTransport(
        provider=QuoteProbeSource.ODDSPAPI,
        external_event_id="id1000001",
        upstream=upstream,
    )
    catalog = {"apiKey": "test-key", "language": "en"}
    odds = {
        "apiKey": "test-key",
        "fixtureId": "id1000001",
        "oddsFormat": "decimal",
        "language": "en",
        "verbosity": "3",
    }
    _blocked(guard, "https://api.oddspapi.io/v4/odds", odds)
    _blocked(guard, "https://api.oddspapi.io/v4/odds", {**odds, "fixtureId": "another"})
    _request(guard, "https://api.oddspapi.io/v4/markets", catalog)
    _blocked(guard, "https://api.oddspapi.io/v4/markets", catalog)
    _request(guard, "https://api.oddspapi.io/v4/odds", odds)
    _blocked(guard, "https://api.oddspapi.io/v4/odds", odds)
    _blocked(guard, "https://api.oddspapi.io/v4/settlements", odds)
    assert len(upstream.calls) == 2
    assert guard.attempts == {"/v4/markets": 1, "/v4/odds": 1}


def test_failed_quote_request_also_uses_the_attempt_budget() -> None:
    upstream = _Recorder(fails=True)
    guard = QuoteProbeTransport(
        provider=QuoteProbeSource.THE_ODDS_API,
        external_event_id="id123",
        upstream=upstream,
    )
    url = "https://api.the-odds-api.com/v4/sports/soccer_epl/events/id123/odds"
    q = {
        "apiKey": "test-key",
        "regions": "eu",
        "markets": "h2h",
        "dateFormat": "iso",
        "oddsFormat": "decimal",
        "includeSids": "false",
    }
    _blocked(guard, url, q)
    _blocked(guard, url, q)
    assert len(upstream.calls) == 1
    assert sum(guard.attempts.values()) == 1


def test_quote_probe_rejects_malformed_event_ids() -> None:
    for event_id in ("", "../odds", "other?apiKey=secret", "slash/path", " "):
        try:
            QuoteProbeTransport(
                provider=QuoteProbeSource.THE_ODDS_API,
                external_event_id=event_id,
                upstream=_Recorder(),
            )
        except ValueError:
            continue
        raise AssertionError("malformed event id was accepted")


def test_missing_local_credentials_cannot_start_quota_check() -> None:
    output = StringIO()
    with (
        patch("sys.argv", ["prepare_live_odds", "--check-quotas"]),
        patch.dict("os.environ", {"THE_ODDS_API_KEY": "", "ODDSPAPI_API_KEY": ""}),
        redirect_stdout(output),
    ):
        assert main() == 2
    assert "no requests made" in output.getvalue()
