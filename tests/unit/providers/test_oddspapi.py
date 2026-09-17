"""Phase 16.3 unit tests for the OddsPapi second-source adapter."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from arbiscan.domain import ProviderId, Sport
from arbiscan.observability.provider import InMemoryProviderTelemetry, ProviderTelemetryOutcome
from arbiscan.providers import ProviderError, ProviderErrorKind, ProviderHealthState
from arbiscan.providers.http import HttpResponse
from arbiscan.providers.oddspapi import ODDSPAPI_PROVIDER_ID, OddsPapiConfig, OddsPapiProvider

NOW = datetime(2026, 9, 17, 10, 30, tzinfo=UTC)
FIXTURE_KEY = "synthetic-oddspapi-key"
FIXTURE_ID = "id1000001761301153"


@dataclass(frozen=True, slots=True)
class _Request:
    path: str
    query: Mapping[str, str]
    timeout_seconds: float


class _SyntheticOddsPapiTransport:
    """Hand-authored schema-faithful transport; no captured vendor payloads."""

    def __init__(
        self,
        *,
        status_overrides: Mapping[str, int] | None = None,
        fixture_status_id: int = 0,
        fixture_status_name: str = "Pre-Game",
        malformed_path: str | None = None,
    ) -> None:
        self.status_overrides = dict(status_overrides or {})
        self.fixture_status_id = fixture_status_id
        self.fixture_status_name = fixture_status_name
        self.malformed_path = malformed_path
        self.requests: list[_Request] = []

    async def get(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        path = urlparse(url).path.removeprefix("/v4")
        self.requests.append(
            _Request(path=path, query=dict(query), timeout_seconds=timeout_seconds)
        )
        status = self.status_overrides.get(path, 200)
        if status != 200:
            headers = {"Retry-After": "7"} if status == 429 else {}
            return HttpResponse(status_code=status, headers=headers, body=b'{"error":"synthetic"}')
        if path == self.malformed_path:
            return HttpResponse(status_code=200, headers={}, body=b'{"unexpected":true}')
        payload = self._payload(path, query)
        return HttpResponse(
            status_code=200,
            headers={},
            body=json.dumps(payload, separators=(",", ":")).encode(),
        )

    def _payload(self, path: str, query: Mapping[str, str]) -> Any:
        if path == "/sports":
            return [
                {"sportId": 10, "slug": "soccer", "sportName": "Soccer"},
                {"sportId": 11, "slug": "basketball", "sportName": "Basketball"},
                {"sportId": 12, "slug": "tennis", "sportName": "Tennis"},
            ]
        if path == "/tournaments":
            if query.get("sportId") == "10":
                return [
                    {
                        "tournamentId": 17,
                        "tournamentSlug": "premier-league",
                        "tournamentName": "Premier League",
                        "categorySlug": "england",
                        "categoryName": "England",
                        "futureFixtures": 12,
                        "upcomingFixtures": 2,
                        "liveFixtures": 1,
                    }
                ]
            return [
                {
                    "tournamentId": 2591,
                    "tournamentSlug": "us-open-men",
                    "tournamentName": "US Open Men",
                    "categorySlug": "atp",
                    "categoryName": "ATP",
                    "futureFixtures": 8,
                    "upcomingFixtures": 1,
                    "liveFixtures": 0,
                }
            ]
        if path == "/fixtures":
            return [self._fixture()]
        if path == "/markets":
            return [
                {
                    "marketId": 101,
                    "marketLength": 3,
                    "marketName": "Full Time Result",
                    "playerProp": False,
                    "sportId": 10,
                    "handicap": 0,
                    "period": "fulltime",
                    "marketType": "1x2",
                    "outcomes": [
                        {"outcomeId": 101, "outcomeName": "1"},
                        {"outcomeId": 102, "outcomeName": "X"},
                        {"outcomeId": 103, "outcomeName": "2"},
                    ],
                },
                {
                    "marketId": 104,
                    "marketLength": 2,
                    "marketName": "Both Teams To Score",
                    "playerProp": False,
                    "sportId": 10,
                    "handicap": 0,
                    "period": "fulltime",
                    "marketType": "yes_no",
                    "outcomes": [
                        {"outcomeId": 104, "outcomeName": "Yes"},
                        {"outcomeId": 105, "outcomeName": "No"},
                    ],
                },
                {
                    "marketId": 121,
                    "marketLength": 2,
                    "marketName": "Match Winner",
                    "playerProp": False,
                    "sportId": 12,
                    "handicap": 0,
                    "period": "match",
                    "marketType": "winner",
                    "outcomes": [
                        {"outcomeId": 121, "outcomeName": "1"},
                        {"outcomeId": 122, "outcomeName": "2"},
                    ],
                },
                # An unrelated future catalogue shape must not break the MVP parser.
                {
                    "marketId": 999999,
                    "marketName": "Player Special",
                    "sportId": 11,
                },
            ]
        if path == "/odds":
            return self._odds()
        if path == "/account":
            return {
                "api_key": FIXTURE_KEY,
                "current_subscription_id": "sub-1",
                "subscriptions": [
                    {
                        "subscription_id": "sub-1",
                        "is_active": True,
                        "request_limit": 500,
                        "request_count": 123,
                    }
                ],
            }
        raise AssertionError(f"unexpected synthetic endpoint: {path}")

    def _fixture(self) -> dict[str, Any]:
        return {
            "fixtureId": FIXTURE_ID,
            "participant1Id": 35,
            "participant2Id": 34,
            "sportId": 10,
            "tournamentId": 17,
            "seasonId": 130281,
            "statusId": self.fixture_status_id,
            "hasOdds": True,
            "startTime": "2026-09-17T18:00:00.000Z",
            "updatedAt": "2026-09-17T10:15:00.000Z",
            "statusName": self.fixture_status_name,
            "participant1Name": "Liverpool FC",
            "participant2Name": "Manchester United",
            "sportName": "Soccer",
            "tournamentName": "Premier League",
        }

    @staticmethod
    def _price(
        value: float,
        *,
        outcome: str,
        changed_at: str,
        bookmaker_changed_at: str | None,
        active: bool = True,
    ) -> dict[str, Any]:
        return {
            "active": active,
            "betslip": None,
            "bookmakerOutcomeId": outcome,
            "bookmakerChangedAt": bookmaker_changed_at,
            "changedAt": changed_at,
            "limit": 100,
            "playerName": None,
            "price": value,
            "priceAmerican": "100",
            "priceFractional": "1/1",
            "mainLine": True,
            "exchangeMeta": None,
        }

    def _odds(self) -> dict[str, Any]:
        payload = self._fixture()
        payload["bookmakerOdds"] = {
            "pinnacle": {
                "bookmakerIsActive": True,
                "bookmakerFixtureId": "1626291706",
                "fixturePath": "https://example.invalid/fixture",
                "suspended": False,
                "markets": {
                    "101": {
                        "bookmakerMarketId": "ft-result",
                        "marketActive": True,
                        "outcomes": {
                            "101": {
                                "players": {
                                    "0": self._price(
                                        2.4,
                                        outcome="home",
                                        changed_at="2026-09-17T10:20:01Z",
                                        bookmaker_changed_at="2026-09-17T10:20:00Z",
                                    )
                                }
                            },
                            "102": {
                                "players": {
                                    "0": self._price(
                                        3.2,
                                        outcome="draw",
                                        changed_at="2026-09-17T10:20:02Z",
                                        bookmaker_changed_at=None,
                                    )
                                }
                            },
                            "103": {
                                "players": {
                                    "0": self._price(
                                        3.1,
                                        outcome="away",
                                        changed_at="2026-09-17T10:20:03Z",
                                        bookmaker_changed_at=None,
                                    )
                                }
                            },
                        },
                    },
                    # Broader OddsPapi market data is deliberately ignored in Phase 16.3.
                    "104": {
                        "bookmakerMarketId": "btts",
                        "marketActive": True,
                        "outcomes": {},
                    },
                },
            }
        }
        return payload


def _build(
    *,
    transport: _SyntheticOddsPapiTransport | None = None,
) -> tuple[OddsPapiProvider, _SyntheticOddsPapiTransport, InMemoryProviderTelemetry]:
    fixture_transport = transport or _SyntheticOddsPapiTransport()
    telemetry = InMemoryProviderTelemetry()
    provider = OddsPapiProvider(
        config=OddsPapiConfig(api_key=FIXTURE_KEY),
        transport=fixture_transport,
        telemetry=telemetry,
        clock=lambda: NOW,
    )
    return provider, fixture_transport, telemetry


def _discover_football_event(provider: OddsPapiProvider) -> None:
    competitions = asyncio.run(provider.discover_competitions(Sport.FOOTBALL))
    assert tuple(value.external_id for value in competitions) == ("17",)
    events = asyncio.run(provider.discover_events("17"))
    assert tuple(value.external_id for value in events) == (FIXTURE_ID,)


def test_config_repr_hides_credential() -> None:
    config = OddsPapiConfig(api_key=FIXTURE_KEY)
    assert FIXTURE_KEY not in repr(config)


def test_discovery_maps_only_phase16_supported_sports() -> None:
    provider, _transport, _telemetry = _build()

    sports = asyncio.run(provider.supported_sports())
    football = asyncio.run(provider.discover_competitions(Sport.FOOTBALL))
    events = asyncio.run(provider.discover_events("17"))

    assert sports == (Sport.FOOTBALL, Sport.TENNIS)
    assert tuple(value.name for value in football) == ("Premier League",)
    assert len(events) == 1
    assert events[0].sport is Sport.FOOTBALL
    assert tuple(value.name for value in events[0].participants) == (
        "Liverpool FC",
        "Manchester United",
    )


def test_odds_preserve_price_origin_and_selection_level_freshness() -> None:
    provider, transport, telemetry = _build()
    _discover_football_event(provider)

    snapshot = asyncio.run(provider.fetch_odds(FIXTURE_ID))

    assert snapshot is not None
    assert snapshot.provider_id == ODDSPAPI_PROVIDER_ID
    assert len(snapshot.markets) == 3
    assert {
        market.price_provider.id for market in snapshot.markets if market.price_provider is not None
    } == {ProviderId("bookmaker:the-odds-api:pinnacle")}
    assert {market.selections[0].label for market in snapshot.markets} == {"1", "X", "2"}
    assert {market.source_timestamp for market in snapshot.markets} == {
        datetime(2026, 9, 17, 10, 20, 0, tzinfo=UTC),
        datetime(2026, 9, 17, 10, 20, 2, tzinfo=UTC),
        datetime(2026, 9, 17, 10, 20, 3, tzinfo=UTC),
    }
    assert all(market.source_status == "active" for market in snapshot.markets)
    assert all(market.selections[0].source_status == "active" for market in snapshot.markets)

    odds_request = next(request for request in transport.requests if request.path == "/odds")
    assert odds_request.query["apiKey"] == FIXTURE_KEY
    assert odds_request.query["oddsFormat"] == "decimal"
    assert odds_request.query["verbosity"] == "3"
    assert FIXTURE_KEY not in repr(telemetry.events)
    assert telemetry.events[-1].outcome is ProviderTelemetryOutcome.SUCCESS


def test_non_prematch_odds_fail_closed_as_suspended() -> None:
    provider, _transport, _telemetry = _build(
        transport=_SyntheticOddsPapiTransport(
            fixture_status_id=1,
            fixture_status_name="Live",
        )
    )
    _discover_football_event(provider)

    snapshot = asyncio.run(provider.fetch_odds(FIXTURE_ID))

    assert snapshot is not None
    assert snapshot.markets
    assert all(market.source_status == "suspended" for market in snapshot.markets)
    assert all(
        selection.source_status == "suspended"
        for market in snapshot.markets
        for selection in market.selections
    )


def test_account_quota_maps_to_shared_rate_limit_snapshot_without_secret_leakage() -> None:
    provider, _transport, telemetry = _build()

    rate_limit = asyncio.run(provider.rate_limit())

    assert rate_limit is not None
    assert rate_limit.provider_id == ODDSPAPI_PROVIDER_ID
    assert rate_limit.limit == 500
    assert rate_limit.remaining == 377
    assert FIXTURE_KEY not in repr(rate_limit)
    assert FIXTURE_KEY not in repr(telemetry.events)


def test_rate_limit_error_is_retryable_but_arbitrary_client_error_is_not() -> None:
    limited, _transport, _telemetry = _build(
        transport=_SyntheticOddsPapiTransport(status_overrides={"/sports": 429})
    )
    rejected, _transport2, _telemetry2 = _build(
        transport=_SyntheticOddsPapiTransport(status_overrides={"/sports": 400})
    )

    try:
        asyncio.run(limited.supported_sports())
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.RATE_LIMITED
        assert error.retryable
        assert error.retry_after == timedelta(seconds=7)
        assert FIXTURE_KEY not in str(error)
    else:
        raise AssertionError("expected rate-limit ProviderError")

    try:
        asyncio.run(rejected.supported_sports())
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.INVALID_REQUEST
        assert not error.retryable
        assert FIXTURE_KEY not in str(error)
    else:
        raise AssertionError("expected invalid-request ProviderError")


def test_health_validates_payload_and_never_exposes_credential() -> None:
    provider, _transport, _telemetry = _build(
        transport=_SyntheticOddsPapiTransport(malformed_path="/sports")
    )

    health = asyncio.run(provider.health())

    assert health.state is ProviderHealthState.DEGRADED
    assert health.detail is not None
    assert "malformed_response" in health.detail
    assert FIXTURE_KEY not in health.detail
