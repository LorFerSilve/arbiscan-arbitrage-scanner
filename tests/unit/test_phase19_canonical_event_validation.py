"""Network-free checks for the non-executable EPL Phase-7/8 review."""

from datetime import UTC, datetime, timedelta

from scripts.validate_epl_identity import validate_epl_identity

from arbiscan.domain import Sport
from arbiscan.providers import SourceCompetition, SourceEvent, SourceParticipant

_START = datetime(2026, 10, 31, 12, 30, tzinfo=UTC)
_ODDS_COMP = SourceCompetition("soccer_epl", Sport.FOOTBALL, "EPL", "Soccer")
_PAPI_COMP = SourceCompetition("17", Sport.FOOTBALL, "Premier League", "England")


def _fixture(
    event_id: str,
    home: str,
    away: str,
    *,
    odds: bool = False,
    start: datetime = _START,
    status: str = "Pre-Game",
) -> SourceEvent:
    return SourceEvent(
        external_id=event_id,
        sport=Sport.FOOTBALL,
        competition_external_id="soccer_epl" if odds else "17",
        participants=(
            SourceParticipant("p1", home, "home" if odds else "participant1"),
            SourceParticipant("p2", away, "away" if odds else "participant2"),
        ),
        scheduled_start=start,
        source_status="unknown" if odds else status,
    )


def _review(
    odds_events: tuple[SourceEvent, ...],
    papi_events: tuple[SourceEvent, ...],
    *,
    odds_comp: SourceCompetition = _ODDS_COMP,
    papi_comp: SourceCompetition = _PAPI_COMP,
):
    return validate_epl_identity(odds_comp, odds_events, papi_comp, papi_events)


def test_explict_team_aliases_and_competition_use_phase7_phase8_without_quote_eligibility() -> None:
    odds = _fixture("odds-1", "Chelsea", "Manchester United", odds=True)
    papi = _fixture("papi-1", "Chelsea FC", "Manchester United FC")
    report = _review((odds,), (papi,))

    assert report.provisional_pairs == ((odds, papi),)
    assert report.quote_eligible_pairs == 0
    assert report.apparent_reversed_order == 0
    assert report.unresolved_papi_events == 0


def test_opposite_participant_order_stays_blocked_and_is_flagged() -> None:
    odds = _fixture("odds-1", "Chelsea", "Manchester United", odds=True)
    papi = _fixture("papi-1", "Manchester United FC", "Chelsea FC")
    report = _review((odds,), (papi,))

    assert report.provisional_pairs == ((odds, papi),)
    assert report.apparent_reversed_order == 1
    assert report.quote_eligible_pairs == 0


def test_unapproved_or_youth_and_womens_teams_are_not_guessed() -> None:
    odds = _fixture("odds-1", "Chelsea", "Manchester United", odds=True)
    papi_events = (
        _fixture("papi-women", "Chelsea Women", "Manchester United"),
        _fixture("papi-youth", "Chelsea U21", "Manchester United"),
        _fixture("papi-unknown", "Manchester Utd", "Chelsea"),
    )
    report = _review((odds,), papi_events)

    assert report.provisional_pairs == ()
    assert report.unresolved_papi_events == 3
    assert report.quote_eligible_pairs == 0


def test_competition_context_and_anchor_roles_fail_closed() -> None:
    odds = _fixture("odds-1", "Chelsea", "Manchester United", odds=True)
    papi = _fixture("papi-1", "Chelsea", "Manchester United")
    wrong_comp = SourceCompetition("17", Sport.FOOTBALL, "Premier League", "Bangladesh")
    report = _review((odds,), (papi,), papi_comp=wrong_comp)
    assert not report.provisional_pairs
    assert report.unresolved_papi_events == 1

    wrong_anchor = SourceEvent(
        external_id="odds-bad-roles",
        sport=Sport.FOOTBALL,
        competition_external_id="soccer_epl",
        participants=(
            SourceParticipant("p1", "Chelsea", "participant1"),
            SourceParticipant("p2", "Manchester United", "participant2"),
        ),
        scheduled_start=_START,
    )
    report = _review((wrong_anchor,), (papi,))
    assert report.excluded_odds_events == 1
    assert not report.provisional_pairs


def test_large_start_delta_and_in_play_status_are_blocked() -> None:
    odds = _fixture("odds-1", "Chelsea", "Manchester United", odds=True)
    late = _fixture(
        "papi-late",
        "Chelsea",
        "Manchester United",
        start=_START + timedelta(minutes=6),
    )
    live = _fixture("papi-live", "Chelsea", "Manchester United", status="In-Play")
    report = _review((odds,), (late, live))
    assert report.provisional_pairs == ()
    assert report.unresolved_papi_events == 2


def test_duplicate_provider_fixtures_cannot_bind_to_one_canonical_anchor() -> None:
    odds = _fixture("odds-1", "Chelsea", "Manchester United", odds=True)
    papi = (
        _fixture("papi-1", "Chelsea FC", "Manchester United"),
        _fixture("papi-2", "Chelsea", "Manchester United FC"),
    )
    report = _review((odds,), papi)
    assert not report.provisional_pairs
    assert report.unresolved_papi_events == 2
    assert report.quote_eligible_pairs == 0


def test_ambiguous_canonical_anchors_are_not_promoted() -> None:
    odds = (
        _fixture("odds-1", "Chelsea", "Manchester United", odds=True),
        _fixture("odds-2", "Chelsea", "Manchester United", odds=True),
    )
    papi = _fixture("papi-1", "Chelsea FC", "Manchester United")
    report = _review(odds, (papi,))
    assert report.provisional_pairs == ()
    assert report.ambiguous_papi_events == 1


def test_seven_named_discovery_candidates_are_reviewable_not_quoteable() -> None:
    names = (
        ("Chelsea", "Manchester United"),
        ("Hull City", "Ipswich Town"),
        ("Brentford", "Nottingham Forest"),
        ("Tottenham Hotspur", "Crystal Palace"),
        ("Aston Villa", "Fulham"),
        ("Liverpool", "Arsenal"),
        ("Newcastle United", "Everton"),
    )
    odds = tuple(
        _fixture(
            f"odds-{i}",
            home,
            away,
            odds=True,
            start=_START + timedelta(hours=i * 4),
        )
        for i, (home, away) in enumerate(names)
    )
    papi = tuple(
        _fixture(
            f"papi-{i}",
            f"{home} FC",
            f"{away} FC",
            start=_START + timedelta(hours=i * 4),
        )
        for i, (home, away) in enumerate(names)
    )
    report = _review(odds, papi)
    assert len(report.provisional_pairs) == 7
    assert report.quote_eligible_pairs == 0
    assert report.apparent_reversed_order == 0
    assert report.unresolved_papi_events == 0

def test_two_labels_for_same_club_cannot_become_valid_participants() -> None:
    odds = _fixture("odds-1", "Chelsea", "Manchester United", odds=True)
    papi = _fixture("papi-invalid", "Chelsea", "Chelsea FC")
    report = _review((odds,), (papi,))
    assert report.provisional_pairs == ()
    assert report.unresolved_papi_events == 1
    assert report.quote_eligible_pairs == 0
