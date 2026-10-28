"""Network-free regression checks for the one-shot discovery guardrails."""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from scripts.discover_live_overlap import (
    DiscoveryOnlyTransport,
    _england_premier_league,
    candidate_pairs,
)

from arbiscan.domain import Sport
from arbiscan.providers import (
    HttpResponse,
    HttpTransportError,
    SourceCompetition,
    SourceEvent,
    SourceParticipant,
)


class _FakeHttpTransport:
    def __init__(self) -> None:
        self.calls = 0

    async def get(
        self, *, url: str, query: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        self.calls += 1
        return HttpResponse(status_code=200, headers={}, body=b"[]")


def _event(
    event_id: str,
    a: str,
    b: str,
    *,
    minutes: int = 0,
    status: str = "Pre-Game",
) -> SourceEvent:
    return SourceEvent(
        external_id=event_id,
        sport=Sport.FOOTBALL,
        competition_external_id="premier",
        participants=(
            SourceParticipant(external_id="p1", name=a),
            SourceParticipant(external_id="p2", name=b),
        ),
        scheduled_start=datetime(2026, 11, 1, 15, tzinfo=UTC) + timedelta(minutes=minutes),
        source_status=status,
    )


def test_unique_matching_candidate_allows_fc_suffix_and_small_clock_skew() -> None:
    odds = _event("api", "Liverpool", "Manchester United")
    papi = _event("papi", "Liverpool FC", "Manchester United FC", minutes=2)
    assert candidate_pairs((odds,), (papi,)) == ((odds, papi),)


def test_ambiguous_matches_and_larger_time_differences_fail_closed() -> None:
    odds = _event("api", "Liverpool", "Manchester United")
    a = _event("a", "Liverpool FC", "Manchester United", minutes=2)
    b = _event("b", "Liverpool", "Manchester United FC", minutes=1)
    assert candidate_pairs((odds,), (a, b)) == ()
    assert (
        candidate_pairs((odds,), (_event("late", "Liverpool", "Manchester United", minutes=6),))
        == ()
    )


def test_papi_league_must_be_unique_in_england() -> None:
    england = SourceCompetition("1", Sport.FOOTBALL, "Premier League", "England")
    other = SourceCompetition("2", Sport.FOOTBALL, "Premier League", "Saudi Arabia")
    assert _england_premier_league((england, other)) == england
    duplicate = SourceCompetition("3", Sport.FOOTBALL, "Premier League", "England")
    assert _england_premier_league((england, duplicate)) is None


def test_transport_caps_every_billable_attempt_and_blocks_odds() -> None:
    fake = _FakeHttpTransport()
    transport = DiscoveryOnlyTransport(
        host="api.oddspapi.io",
        routes=frozenset({"/v4/account", "/v4/sports", "/v4/odds"}),
        billable_routes=frozenset({"/v4/sports", "/v4/odds"}),
        max_billable=1,
        upstream=fake,
    )

    async def scenario() -> None:
        await transport.get(url="https://api.oddspapi.io/v4/account", query={}, timeout_seconds=1)
        await transport.get(url="https://api.oddspapi.io/v4/sports", query={}, timeout_seconds=1)
        for url in (
            "https://api.oddspapi.io/v4/odds",
            "https://malicious.example/v4/account",
        ):
            try:
                await transport.get(url=url, query={}, timeout_seconds=1)
            except HttpTransportError:
                pass
            else:
                raise AssertionError("unauthorized API call was not blocked")

    asyncio.run(scenario())
    assert transport.billable_attempts == 1
    assert fake.calls == 2
