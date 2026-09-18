"""Phase 17.11 canonical tournament/championship outright regressions."""

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

COMPETITION_ID = CompetitionId("competition:phase17-11:championship")
EVENT_ID = EventId("event:phase17-11:championship-winner")
MARKET_ID = MarketId("market:phase17-11:championship-winner")


def _participants() -> tuple[Participant, ...]:
    return tuple(
        Participant(
            id=ParticipantId(f"participant:phase17-11:{slug}"),
            sport=Sport.FOOTBALL,
            name=name,
            kind=ParticipantKind.TEAM,
        )
        for slug, name in (
            ("arsenal", "Arsenal"),
            ("bayern", "Bayern Munich"),
            ("inter", "Inter"),
            ("real-madrid", "Real Madrid"),
        )
    )


def _graph(
    *,
    participants: tuple[Participant, ...] | None = None,
) -> tuple[Competition, tuple[Participant, ...], Event, Market, tuple[Selection, ...]]:
    candidates = participants or _participants()
    competition = Competition(
        id=COMPETITION_ID,
        sport=Sport.FOOTBALL,
        name="European Championship Outright",
        region="Europe",
        season="2026/27",
    )
    event = Event(
        id=EVENT_ID,
        sport=Sport.FOOTBALL,
        competition=competition,
        participants=candidates,
        scheduled_start=datetime(2026, 9, 18, 18, 0, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
    )
    market = Market(
        id=MARKET_ID,
        event_id=EVENT_ID,
        kind=MarketKind.OUTRIGHT_WINNER,
        period=MarketPeriod.TOURNAMENT,
    )
    selections = tuple(
        Selection(
            id=SelectionId(f"selection:phase17-11:{participant.id.value.rsplit(':', 1)[-1]}"),
            market_id=MARKET_ID,
            kind=SelectionKind.PARTICIPANT,
            participant_id=participant.id,
        )
        for participant in candidates
    )
    return competition, candidates, event, market, selections


def _registry(
    *,
    participants: tuple[Participant, ...] | None = None,
    selections: tuple[Selection, ...] | None = None,
) -> CanonicalRegistry:
    competition, candidates, event, market, complete = _graph(participants=participants)
    return CanonicalRegistry(
        competitions=(competition,),
        participants=candidates,
        events=(event,),
        markets=(market,),
        selections=complete if selections is None else selections,
    )


def test_tournament_outright_requires_exact_complete_candidate_set() -> None:
    registry = _registry()

    assert set(registry.selection_ids_for_market(MARKET_ID)) == {
        SelectionId("selection:phase17-11:arsenal"),
        SelectionId("selection:phase17-11:bayern"),
        SelectionId("selection:phase17-11:inter"),
        SelectionId("selection:phase17-11:real-madrid"),
    }

    _competition, _participants_value, _event, _market, complete = _graph()
    try:
        _registry(selections=complete[:-1])
    except ValueError as error:
        assert "one participant selection per event participant" in str(error)
    else:
        raise AssertionError("incomplete outright candidate set must fail closed")


def test_tournament_outright_rejects_mixed_participant_kinds_and_synthetic_field_candidate() -> (
    None
):
    candidates = _participants()
    synthetic_field = replace(
        candidates[-1],
        id=ParticipantId("participant:phase17-11:field"),
        name="Field",
        kind=ParticipantKind.OTHER,
    )
    mixed = (*candidates[:-1], synthetic_field)

    try:
        _registry(participants=mixed)
    except ValueError as error:
        assert "one participant kind" in str(error)
    else:
        raise AssertionError("mixed team/Field outright candidate set must fail closed")


def test_outcome_selections_must_cover_only_canonical_event_candidates() -> None:
    competition, candidates, event, market, complete = _graph()
    invalid = replace(
        complete[-1],
        kind=SelectionKind.YES,
        participant_id=None,
    )

    try:
        CanonicalRegistry(
            competitions=(competition,),
            participants=candidates,
            events=(event,),
            markets=(market,),
            selections=(*complete[:-1], invalid),
        )
    except ValueError as error:
        assert "one participant selection per event participant" in str(error)
    else:
        raise AssertionError("special non-participant outright outcome must fail closed")
