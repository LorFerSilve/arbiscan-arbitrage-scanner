"""Offline checks for bounded live metadata-only provider ID verification."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from contextlib import redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import patch

from scripts.audit_official_fixture import (
    observed_provider_ids_for_official_fixture,
    unique_official_odds_anchor,
)
from scripts.discover_live_overlap import main, run_discovery
from scripts.validate_epl_identity import validate_epl_identity

from arbiscan.domain import Sport
from arbiscan.normalization.football_1x2 import FixtureSideAlignment
from arbiscan.providers import (
    HttpResponse,
    SourceCompetition,
    SourceEvent,
    SourceParticipant,
)
from tests.support.oddspapi import FixtureHttpTransport as PapiFixtureTransport
from tests.support.the_odds_api import FixtureHttpTransport as OddsFixtureTransport

_START = datetime(2026, 10, 31, 12, 30, tzinfo=UTC)
_NOW = datetime(2026, 10, 28, 11, 0, tzinfo=UTC)
_ODDS_COMP = SourceCompetition("soccer_epl", Sport.FOOTBALL, "EPL", "Soccer")
_PAPI_COMP = SourceCompetition("17", Sport.FOOTBALL, "Premier League", "England")


def _event(
    *,
    odds: bool,
    source_id: str,
    home: str = "Chelsea",
    away: str = "Manchester United",
    home_id: str = "35",
    away_id: str = "34",
) -> SourceEvent:
    return SourceEvent(
        external_id=source_id,
        sport=Sport.FOOTBALL,
        competition_external_id="soccer_epl" if odds else "17",
        participants=(
            SourceParticipant(
                home_id,
                home,
                "home" if odds else "participant1",
            ),
            SourceParticipant(
                away_id,
                away,
                "away" if odds else "participant2",
            ),
        ),
        scheduled_start=_START,
        source_status="unknown" if odds else "Pre-Game",
    )


class _OddsEventsTransport:
    """Fixture-backed free discovery; never perform outbound I/O."""

    def __init__(self, events: list[dict[str, object]]) -> None:
        self.fixture = OddsFixtureTransport()
        self.events = events
        self.calls: list[str] = []

    async def get(
        self, *, url: str, query: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        self.calls.append(url)
        if url.endswith("/sports/soccer_epl/events"):
            return HttpResponse(
                status_code=200,
                headers={"x-requests-remaining": "400", "x-requests-used": "0"},
                body=json.dumps(self.events).encode("utf-8"),
            )
        return await self.fixture.get(url=url, query=query, timeout_seconds=timeout_seconds)


def _raw_odds_event(*, home: str = "Chelsea", away: str = "Manchester United") -> dict[str, object]:
    return {
        "id": "real-odds-api-123",
        "sport_key": "soccer_epl",
        "sport_title": "EPL",
        "commence_time": "2026-10-31T12:30:00Z",
        "home_team": home,
        "away_team": away,
    }


def _raw_papi_event(
    *, participant1: str = "Chelsea FC", participant2: str = "Manchester United"
) -> dict[str, object]:
    return {
        "fixtureId": "id1000001761309999",
        "participant1Id": 35,
        "participant2Id": 34,
        "sportId": 10,
        "tournamentId": 17,
        "seasonId": 130281,
        "statusId": 0,
        "hasOdds": True,
        "startTime": "2026-10-31T12:30:00.000Z",
        "updatedAt": "2026-10-28T11:00:00.000Z",
        "statusName": "Pre-Game",
        "participant1Name": participant1,
        "participant2Name": participant2,
        "sportName": "Soccer",
        "tournamentName": "Premier League",
    }


def _run(
    odds_events: list[dict[str, object]],
    papi_events: list[dict[str, object]],
) -> tuple[int, str, _OddsEventsTransport, PapiFixtureTransport]:
    odds = _OddsEventsTransport(odds_events)
    papi = PapiFixtureTransport(
        body_overrides={"/fixtures": json.dumps(papi_events).encode("utf-8")}
    )
    output = StringIO()
    with redirect_stdout(output):
        result = asyncio.run(
            run_discovery(
                "secret-odds-key",
                "secret-papi-key",
                verify_official=True,
                reference_now=_NOW,
                odds_upstream=odds,
                papi_upstream=papi,
            )
        )
    return result, output.getvalue(), odds, papi


def test_official_reference_reports_real_source_ids_without_quote_approval() -> None:
    a = _event(
        odds=True,
        source_id="real-odds-api-123",
        home_id="name:Chelsea",
        away_id="name:Manchester United",
    )
    b = _event(odds=False, source_id="id1000001761309999")
    review = validate_epl_identity(_ODDS_COMP, (a,), _PAPI_COMP, (b,))
    report = observed_provider_ids_for_official_fixture(review)
    assert report is not None
    assert report.the_odds_api_event_id == "real-odds-api-123"
    assert report.oddspapi_fixture_id == "id1000001761309999"
    assert report.oddspapi_competition_id == "17"
    assert (report.oddspapi_participant1_id, report.oddspapi_participant2_id) == ("35", "34")
    assert report.oddspapi_order_vs_official is FixtureSideAlignment.ALIGNED
    assert not report.quote_eligible


def test_reversed_participants_are_observed_not_assumed_home_away() -> None:
    odds = _event(odds=True, source_id="good-odds")
    papi = _event(odds=False, source_id="good-papi", home="Manchester United", away="Chelsea")
    review = validate_epl_identity(_ODDS_COMP, (odds,), _PAPI_COMP, (papi,))
    evidence = observed_provider_ids_for_official_fixture(review)
    assert evidence is not None
    assert evidence.oddspapi_order_vs_official is FixtureSideAlignment.REVERSED
    assert not evidence.quote_eligible


def test_malformed_ids_and_duplicates_are_rejected_without_leaking_values() -> None:
    good_odds = _event(odds=True, source_id="real-odds")
    malicious_odds = _event(odds=True, source_id="bad/odds?apiKey=secret")
    assert unique_official_odds_anchor((good_odds, malicious_odds)) is None
    assert unique_official_odds_anchor((good_odds, good_odds)) is None
    assert unique_official_odds_anchor((malicious_odds,)) is None

    papi = _event(odds=False, source_id="id1000001761309999")
    a_review = validate_epl_identity(_ODDS_COMP, (malicious_odds,), _PAPI_COMP, (papi,))
    assert observed_provider_ids_for_official_fixture(a_review) is None


def test_live_metadata_inspection_success_is_three_calls_and_zero_odds() -> None:
    result, output, odds, papi = _run(
        [_raw_odds_event()],
        [_raw_papi_event()],
    )
    assert result == 0
    assert "The Odds API observed soccer_epl event ID: real-odds-api-123" in output
    assert "OddsPapi observed fixtureId: id1000001761309999" in output
    assert "OddsPapi participant1Id: 35 (Chelsea FC)" in output
    assert "OddsPapi participant2Id: 34 (Manchester United)" in output
    assert "ALIGNED" in output
    assert "Quote authorization BLOCKED" in output
    assert "OddsPapi billable calls attempted = 3/3" in output
    assert "secret-odds-key" not in output
    assert "secret-papi-key" not in output
    assert len([call for call in odds.calls if call.endswith("/events")]) == 1
    assert [item.path for item in papi.requests] == [
        "/account",
        "/sports",
        "/tournaments",
        "/fixtures",
    ]


def test_no_matching_free_fixture_stops_before_any_paid_papi_requests() -> None:
    result, output, odds, papi = _run(
        [_raw_odds_event(home="Liverpool", away="Arsenal")],
        [_raw_papi_event()],
    )
    assert result == 1
    assert "OddsPapi was not contacted" in output
    assert "OddsPapi billable calls attempted = 0/3" in output
    assert "real-odds-api-123" not in output
    assert not papi.requests
    assert len(odds.calls) == 2


def test_duplicate_free_source_match_stops_before_paid_requests() -> None:
    result, output, _odds, papi = _run(
        [_raw_odds_event(), _raw_odds_event()],
        [_raw_papi_event()],
    )
    assert result == 1
    assert "OddsPapi was not contacted" in output
    assert not papi.requests


def test_papi_conflicting_identity_consumes_only_metadata_budget() -> None:
    result, output, _odds, papi = _run(
        [_raw_odds_event()],
        [_raw_papi_event(participant1="Chelsea Women")],
    )
    assert result == 1
    assert "no unique Phase 7/8 pair" in output
    assert "OddsPapi billable calls attempted = 3/3" in output
    assert "OddsPapi observed fixtureId:" not in output
    assert all(item.path not in {"/odds", "/markets", "/fixture"} for item in papi.requests)


def test_cli_requires_explicit_execute_and_rejects_odds_only() -> None:
    for argv in (
        ["discover_live_overlap", "--verify-official"],
        ["discover_live_overlap", "--execute", "--verify-official", "--odds-only"],
    ):
        output = StringIO()
        with patch("sys.argv", argv), redirect_stdout(output):
            assert main() == 2
        assert "No API requests made" in output.getvalue()
