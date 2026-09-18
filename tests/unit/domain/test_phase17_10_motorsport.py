"""Phase 17.10 canonical motorsport identity and completeness regressions."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from arbiscan.domain import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventStatus,
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    Participant,
    ParticipantId,
    ParticipantKind,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
)
from arbiscan.matching import CanonicalRegistry
from arbiscan.normalization import MarketSupportStatus, assess_market_support

COMPETITION_ID = CompetitionId("competition:phase17-10:formula1")
EVENT_ID = EventId("event:phase17-10:grand-prix")
VERSTAPPEN_ID = ParticipantId("participant:phase17-10:verstappen")
NORRIS_ID = ParticipantId("participant:phase17-10:norris")
LECLERC_ID = ParticipantId("participant:phase17-10:leclerc")


def _graph() -> tuple[Competition, tuple[Participant, ...], Event]:
    competition = Competition(
        id=COMPETITION_ID,
        sport=Sport.MOTORSPORT,
        name="Formula 1",
        region="International",
    )
    participants = (
        Participant(
            id=VERSTAPPEN_ID,
            sport=Sport.MOTORSPORT,
            name="Max Verstappen",
            kind=ParticipantKind.DRIVER,
        ),
        Participant(
            id=NORRIS_ID,
            sport=Sport.MOTORSPORT,
            name="Lando Norris",
            kind=ParticipantKind.DRIVER,
        ),
        Participant(
            id=LECLERC_ID,
            sport=Sport.MOTORSPORT,
            name="Charles Leclerc",
            kind=ParticipantKind.DRIVER,
        ),
    )
    event = Event(
        id=EVENT_ID,
        sport=Sport.MOTORSPORT,
        competition=competition,
        participants=participants,
        scheduled_start=datetime(2026, 9, 20, 13, 0, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
    )
    return competition, participants, event


def _registry(
    market: Market,
    selections: tuple[Selection, ...],
) -> CanonicalRegistry:
    competition, participants, event = _graph()
    return CanonicalRegistry(
        competitions=(competition,),
        participants=participants,
        events=(event,),
        markets=(market,),
        selections=selections,
    )


def test_motorsport_periods_are_structurally_distinct() -> None:
    race = Market(
        id=MarketId("market:phase17-10:race-winner"),
        event_id=EVENT_ID,
        kind=MarketKind.OUTRIGHT_WINNER,
        period=MarketPeriod.RACE,
    )
    qualifying = replace(
        race,
        id=MarketId("market:phase17-10:qualifying-winner"),
        period=MarketPeriod.QUALIFYING,
    )
    session = replace(
        race,
        id=MarketId("market:phase17-10:session-winner"),
        period=MarketPeriod.SESSION,
    )
    tournament = replace(
        race,
        id=MarketId("market:phase17-10:championship-winner"),
        period=MarketPeriod.TOURNAMENT,
    )

    assert len({race, qualifying, session, tournament}) == 4


def test_podium_finish_requires_explicit_subject_driver() -> None:
    valid = Market(
        id=MarketId("market:phase17-10:verstappen-podium"),
        event_id=EVENT_ID,
        kind=MarketKind.PODIUM_FINISH,
        period=MarketPeriod.RACE,
        subject_participant_id=VERSTAPPEN_ID,
    )
    assert valid.subject_participant_id == VERSTAPPEN_ID

    try:
        Market(
            id=MarketId("market:phase17-10:missing-subject"),
            event_id=EVENT_ID,
            kind=MarketKind.PODIUM_FINISH,
            period=MarketPeriod.RACE,
        )
    except ValueError as error:
        assert "subject_participant_id" in str(error)
    else:
        raise AssertionError("podium market without subject must fail closed")


def test_race_winner_requires_complete_driver_grid() -> None:
    market = Market(
        id=MarketId("market:phase17-10:race-winner"),
        event_id=EVENT_ID,
        kind=MarketKind.OUTRIGHT_WINNER,
        period=MarketPeriod.RACE,
    )
    selections = tuple(
        Selection(
            id=SelectionId(f"selection:phase17-10:winner:{participant_id.value}"),
            market_id=market.id,
            kind=SelectionKind.PARTICIPANT,
            participant_id=participant_id,
        )
        for participant_id in (VERSTAPPEN_ID, NORRIS_ID, LECLERC_ID)
    )

    registry = _registry(market, selections)
    assert set(registry.selection_ids_for_market(market.id)) == {
        selection.id for selection in selections
    }

    try:
        _registry(market, selections[:-1])
    except ValueError as error:
        assert "one participant selection per event participant" in str(error)
    else:
        raise AssertionError("incomplete race-winner grid must fail closed")


def test_podium_finish_requires_exact_yes_no_completeness_and_event_subject() -> None:
    market = Market(
        id=MarketId("market:phase17-10:verstappen-podium"),
        event_id=EVENT_ID,
        kind=MarketKind.PODIUM_FINISH,
        period=MarketPeriod.RACE,
        subject_participant_id=VERSTAPPEN_ID,
    )
    yes = Selection(
        id=SelectionId("selection:phase17-10:podium:yes"),
        market_id=market.id,
        kind=SelectionKind.YES,
    )
    no = Selection(
        id=SelectionId("selection:phase17-10:podium:no"),
        market_id=market.id,
        kind=SelectionKind.NO,
    )
    assert _registry(market, (yes, no)).selection_ids_for_market(market.id)

    invalid_subject = replace(
        market,
        subject_participant_id=ParticipantId("participant:phase17-10:outsider"),
    )
    try:
        _registry(invalid_subject, (yes, no))
    except ValueError as error:
        assert "subject must be one of the event participants" in str(error)
    else:
        raise AssertionError("podium subject outside the event must fail closed")


def test_head_to_head_requires_two_distinct_event_drivers() -> None:
    market = Market(
        id=MarketId("market:phase17-10:h2h:verstappen:norris"),
        event_id=EVENT_ID,
        kind=MarketKind.HEAD_TO_HEAD,
        period=MarketPeriod.RACE,
    )
    first = Selection(
        id=SelectionId("selection:phase17-10:h2h:verstappen"),
        market_id=market.id,
        kind=SelectionKind.PARTICIPANT,
        participant_id=VERSTAPPEN_ID,
    )
    second = Selection(
        id=SelectionId("selection:phase17-10:h2h:norris"),
        market_id=market.id,
        kind=SelectionKind.PARTICIPANT,
        participant_id=NORRIS_ID,
    )
    assert _registry(market, (first, second)).selection_ids_for_market(market.id)

    duplicate = replace(second, participant_id=VERSTAPPEN_ID)
    try:
        _registry(market, (first, duplicate))
    except ValueError as error:
        assert "two distinct participant identities" in str(error)
    else:
        raise AssertionError("same-driver H2H must fail closed")


def test_phase17_10_motorsport_families_remain_runtime_disabled() -> None:
    markets = (
        Market(
            id=MarketId("market:phase17-10:race-winner"),
            event_id=EVENT_ID,
            kind=MarketKind.OUTRIGHT_WINNER,
            period=MarketPeriod.RACE,
        ),
        Market(
            id=MarketId("market:phase17-10:podium"),
            event_id=EVENT_ID,
            kind=MarketKind.PODIUM_FINISH,
            period=MarketPeriod.RACE,
            subject_participant_id=VERSTAPPEN_ID,
        ),
        Market(
            id=MarketId("market:phase17-10:h2h"),
            event_id=EVENT_ID,
            kind=MarketKind.HEAD_TO_HEAD,
            period=MarketPeriod.RACE,
        ),
    )

    for market in markets:
        decision = assess_market_support(sport=Sport.MOTORSPORT, market=market)
        assert decision.status is MarketSupportStatus.UNSUPPORTED
        assert not decision.supported
        assert "DNS/DNF/disqualification/dead-heat" in decision.detail
