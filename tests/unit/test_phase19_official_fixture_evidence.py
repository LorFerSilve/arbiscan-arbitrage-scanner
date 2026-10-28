"""No-network regression coverage for official EPL fixture evidence."""

from datetime import UTC, datetime, timedelta
from io import StringIO
from contextlib import redirect_stdout

from arbiscan.domain import Sport
from arbiscan.normalization.football_1x2 import FixtureSideAlignment
from arbiscan.providers import SourceCompetition, SourceEvent, SourceParticipant
from scripts.audit_official_fixture import (
    OFFICIAL_MATCH_ID,
    audit_official_chelsea_manchester_united,
    main,
)
from scripts.validate_epl_identity import CanonicalReview, validate_epl_identity

_START = datetime(2026, 10, 31, 12, 30, tzinfo=UTC)
_ODDS_COMP = SourceCompetition("soccer_epl", Sport.FOOTBALL, "EPL", "Soccer")
_PAPI_COMP = SourceCompetition("17", Sport.FOOTBALL, "Premier League", "England")


def _event(
    source_id: str,
    team1: str,
    team2: str,
    *,
    odds: bool,
    delta_minutes: int = 0,
    status: str = "Pre-Game",
) -> SourceEvent:
    return SourceEvent(
        external_id=source_id,
        sport=Sport.FOOTBALL,
        competition_external_id="soccer_epl" if odds else "17",
        participants=(
            SourceParticipant("a", team1, "home" if odds else "participant1"),
            SourceParticipant("b", team2, "away" if odds else "participant2"),
        ),
        scheduled_start=_START + timedelta(minutes=delta_minutes),
        source_status="unknown" if odds else status,
    )


def _review(
    odds: tuple[SourceEvent, ...], papi: tuple[SourceEvent, ...]
) -> CanonicalReview:
    return validate_epl_identity(_ODDS_COMP, odds, _PAPI_COMP, papi)


def test_chelsea_official_reference_matches_unique_provisional_fixture_only() -> None:
    a = _event("odds-1", "Chelsea", "Manchester United", odds=True)
    b = _event("papi-1", "Chelsea FC", "Manchester United FC", odds=False)
    result = audit_official_chelsea_manchester_united(_review((a,), (b,)))
    assert result.official_reference_id == OFFICIAL_MATCH_ID
    assert result.reviewed_provisional_pair
    assert result.papi_order_relative_to_official is FixtureSideAlignment.ALIGNED
    assert "remain unverified" in result.reason
    assert not result.provider_ids_independently_verified
    assert not result.can_fetch_quotes


def test_reversed_papi_participants_are_reported_not_mapped_to_home() -> None:
    a = _event("odds-1", "Chelsea", "Manchester United", odds=True)
    b = _event("papi-1", "Manchester United", "Chelsea", odds=False)
    result = audit_official_chelsea_manchester_united(_review((a,), (b,)))
    assert result.reviewed_provisional_pair
    assert result.papi_order_relative_to_official is FixtureSideAlignment.REVERSED
    assert not result.can_fetch_quotes


def test_wrong_team_or_start_or_status_does_not_pass() -> None:
    a = _event("odds-1", "Chelsea", "Manchester United", odds=True)
    others = (
        _event("papi-other", "Liverpool", "Arsenal", odds=False),
        _event("papi-late", "Chelsea", "Manchester United", odds=False, delta_minutes=6),
        _event("papi-live", "Chelsea", "Manchester United", odds=False, status="In-Play"),
    )
    for b in others:
        result = audit_official_chelsea_manchester_united(_review((a,), (b,)))
        assert not result.reviewed_provisional_pair
        assert not result.can_fetch_quotes


def test_official_fixture_must_not_be_inferred_from_another_date() -> None:
    a = _event("odds-1", "Chelsea", "Manchester United", odds=True, delta_minutes=10)
    b = _event("papi-1", "Chelsea", "Manchester United", odds=False, delta_minutes=10)
    result = audit_official_chelsea_manchester_united(_review((a,), (b,)))
    assert not result.reviewed_provisional_pair


def test_duplicate_source_ids_fail_before_official_reference_audit() -> None:
    odds = (
        _event("duplicated", "Chelsea", "Manchester United", odds=True),
        _event("duplicated", "Liverpool", "Arsenal", odds=True),
    )
    papi = (_event("papi-1", "Chelsea", "Manchester United", odds=False),)
    result = audit_official_chelsea_manchester_united(_review(odds, papi))
    assert not result.reviewed_provisional_pair


def test_two_pairs_near_the_official_match_are_not_promoted() -> None:
    # Even individually valid pairs cannot claim unique official reference ownership.
    a = _event("a", "Chelsea", "Manchester United", odds=True)
    b = _event("b", "Chelsea", "Manchester United", odds=False)
    report = CanonicalReview(
        provisional_pairs=((a, b), (a, b)),
        apparent_reversed_order=0,
        unresolved_papi_events=0,
        excluded_odds_events=0,
        ambiguous_papi_events=0,
    )
    result = audit_official_chelsea_manchester_united(report)
    assert not result.reviewed_provisional_pair


def test_offline_cli_does_not_access_any_provider() -> None:
    buffer = StringIO()
    with redirect_stdout(buffer):
        assert main() == 0
    output = buffer.getvalue()
    assert "2645278" in output
    assert "12:30:00+00:00" in output
    assert "NOT VERIFIED" in output
    assert "API attempts = 0" in output
