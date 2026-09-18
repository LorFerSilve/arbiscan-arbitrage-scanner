"""Deterministic explicit identity catalog used by the Phase 5 vertical slice."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from arbiscan.domain import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    Market,
    MarketId,
    MarketKind,
    Participant,
    ParticipantId,
    Selection,
    SelectionId,
    SelectionKind,
)
from arbiscan.providers.models import (
    CanonicalIdHooks,
    SourceCompetition,
    SourceEvent,
    SourceMarket,
    SourceSelectionQuote,
)


@dataclass(frozen=True, slots=True)
class CanonicalRegistry:
    """Small immutable canonical object registry with strict referential validation."""

    competitions: tuple[Competition, ...]
    participants: tuple[Participant, ...]
    events: tuple[Event, ...]
    markets: tuple[Market, ...]
    selections: tuple[Selection, ...]
    _competitions_by_id: Mapping[CompetitionId, Competition] = field(
        init=False, repr=False, compare=False
    )
    _participants_by_id: Mapping[ParticipantId, Participant] = field(
        init=False, repr=False, compare=False
    )
    _events_by_id: Mapping[EventId, Event] = field(init=False, repr=False, compare=False)
    _markets_by_id: Mapping[MarketId, Market] = field(init=False, repr=False, compare=False)
    _selections_by_id: Mapping[SelectionId, Selection] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        competitions = tuple(self.competitions)
        participants = tuple(self.participants)
        events = tuple(self.events)
        markets = tuple(self.markets)
        selections = tuple(self.selections)

        if any(not isinstance(value, Competition) for value in competitions):
            raise ValueError("registry competitions must contain Competition values")
        if any(not isinstance(value, Participant) for value in participants):
            raise ValueError("registry participants must contain Participant values")
        if any(not isinstance(value, Event) for value in events):
            raise ValueError("registry events must contain Event values")
        if any(not isinstance(value, Market) for value in markets):
            raise ValueError("registry markets must contain Market values")
        if any(not isinstance(value, Selection) for value in selections):
            raise ValueError("registry selections must contain Selection values")

        competition_map = {value.id: value for value in competitions}
        participant_map = {value.id: value for value in participants}
        event_map = {value.id: value for value in events}
        market_map = {value.id: value for value in markets}
        selection_map = {value.id: value for value in selections}

        if len(competition_map) != len(competitions):
            raise ValueError("registry competition IDs must be unique")
        if len(participant_map) != len(participants):
            raise ValueError("registry participant IDs must be unique")
        if len(event_map) != len(events):
            raise ValueError("registry event IDs must be unique")
        if len(market_map) != len(markets):
            raise ValueError("registry market IDs must be unique")
        if len(selection_map) != len(selections):
            raise ValueError("registry selection IDs must be unique")

        for event in events:
            if event.competition.id not in competition_map:
                raise ValueError("registry event references an unknown competition")
            if any(participant.id not in participant_map for participant in event.participants):
                raise ValueError("registry event references an unknown participant")
        for market in markets:
            if market.event_id not in event_map:
                raise ValueError("registry market references an unknown event")
        for selection in selections:
            selection_market = market_map.get(selection.market_id)
            if selection_market is None:
                raise ValueError("registry selection references an unknown market")
            if selection.kind is SelectionKind.PARTICIPANT:
                participant_id = selection.participant_id
                if participant_id is None or participant_id not in participant_map:
                    raise ValueError(
                        "registry participant selection references an unknown participant"
                    )
                selection_event = event_map[selection_market.event_id]
                if participant_id not in {
                    participant.id for participant in selection_event.participants
                }:
                    raise ValueError(
                        "registry participant selection references a participant outside its event"
                    )

        for market in markets:
            if market.kind is not MarketKind.TOTAL_POINTS:
                continue
            market_selections = tuple(
                selection for selection in selections if selection.market_id == market.id
            )
            if len(market_selections) != 2 or {
                selection.kind for selection in market_selections
            } != {SelectionKind.OVER, SelectionKind.UNDER}:
                raise ValueError(
                    "total-points markets require exactly one OVER and one UNDER selection"
                )

        for market in markets:
            if market.kind is not MarketKind.BOTH_TEAMS_TO_SCORE:
                continue
            market_selections = tuple(
                selection for selection in selections if selection.market_id == market.id
            )
            if len(market_selections) != 2 or {
                selection.kind for selection in market_selections
            } != {SelectionKind.YES, SelectionKind.NO}:
                raise ValueError(
                    "both-teams-to-score markets require exactly one YES and one NO selection"
                )

        for market in markets:
            if market.kind is not MarketKind.SET_WINNER:
                continue
            event = event_map[market.event_id]
            if len(event.participants) != 2:
                raise ValueError("set-winner markets require exactly two event participants")
            market_selections = tuple(
                selection for selection in selections if selection.market_id == market.id
            )
            if len(market_selections) != 2 or any(
                selection.kind is not SelectionKind.PARTICIPANT for selection in market_selections
            ):
                raise ValueError("set-winner markets require exactly two participant selections")
            event_participant_ids = {participant.id for participant in event.participants}
            if {
                selection.participant_id for selection in market_selections
            } != event_participant_ids:
                raise ValueError(
                    "set-winner selections must cover exactly the two event participants"
                )
            if any(selection.handicap is not None for selection in market_selections):
                raise ValueError("set-winner selections must not carry handicaps")

        for market in markets:
            if market.kind is not MarketKind.GAME_WINNER:
                continue
            event = event_map[market.event_id]
            if len(event.participants) != 2:
                raise ValueError("game-winner markets require exactly two event participants")
            market_selections = tuple(
                selection for selection in selections if selection.market_id == market.id
            )
            if len(market_selections) != 2 or any(
                selection.kind is not SelectionKind.PARTICIPANT for selection in market_selections
            ):
                raise ValueError("game-winner markets require exactly two participant selections")
            event_participant_ids = {participant.id for participant in event.participants}
            if {
                selection.participant_id for selection in market_selections
            } != event_participant_ids:
                raise ValueError(
                    "game-winner selections must cover exactly the two event participants"
                )
            if any(selection.handicap is not None for selection in market_selections):
                raise ValueError("game-winner selections must not carry handicaps")

        for market in markets:
            if market.kind is not MarketKind.HANDICAP:
                continue
            event = event_map[market.event_id]
            if len(event.participants) != 2:
                raise ValueError("handicap markets require exactly two ordered event participants")
            market_selections = tuple(
                selection for selection in selections if selection.market_id == market.id
            )
            if len(market_selections) != 2 or any(
                selection.kind is not SelectionKind.PARTICIPANT for selection in market_selections
            ):
                raise ValueError("handicap markets require exactly two participant selections")
            by_participant = {
                selection.participant_id: selection for selection in market_selections
            }
            participant_ids = tuple(participant.id for participant in event.participants)
            if set(by_participant) != set(participant_ids):
                raise ValueError(
                    "handicap selections must cover exactly the two ordered event participants"
                )
            line = market.line
            if line is None:
                raise ValueError("handicap market line is required")
            expected_handicaps = (line, -line)
            for participant_id, expected_handicap in zip(
                participant_ids,
                expected_handicaps,
                strict=True,
            ):
                selection = by_participant[participant_id]
                if selection.handicap != expected_handicap:
                    raise ValueError(
                        "handicap selection values must equal market.line for participant 1 "
                        "and its negation for participant 2"
                    )

        object.__setattr__(self, "competitions", competitions)
        object.__setattr__(self, "participants", participants)
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "markets", markets)
        object.__setattr__(self, "selections", selections)
        object.__setattr__(self, "_competitions_by_id", MappingProxyType(competition_map))
        object.__setattr__(self, "_participants_by_id", MappingProxyType(participant_map))
        object.__setattr__(self, "_events_by_id", MappingProxyType(event_map))
        object.__setattr__(self, "_markets_by_id", MappingProxyType(market_map))
        object.__setattr__(self, "_selections_by_id", MappingProxyType(selection_map))

    def competition(self, competition_id: CompetitionId) -> Competition | None:
        """Return a canonical competition by opaque ID."""
        return self._competitions_by_id.get(competition_id)

    def participant(self, participant_id: ParticipantId) -> Participant | None:
        """Return a canonical participant by opaque ID."""
        return self._participants_by_id.get(participant_id)

    def event(self, event_id: EventId) -> Event | None:
        """Return a canonical event by opaque ID."""
        return self._events_by_id.get(event_id)

    def market(self, market_id: MarketId) -> Market | None:
        """Return a canonical market by opaque ID."""
        return self._markets_by_id.get(market_id)

    def selection(self, selection_id: SelectionId) -> Selection | None:
        """Return a canonical selection by opaque ID."""
        return self._selections_by_id.get(selection_id)

    def selection_ids_for_market(self, market_id: MarketId) -> tuple[SelectionId, ...]:
        """Return deterministic expected outcomes for one canonical market."""
        return tuple(
            sorted(
                (selection.id for selection in self.selections if selection.market_id == market_id),
                key=lambda selection_id: selection_id.value,
            )
        )


@dataclass(frozen=True, slots=True)
class StaticCanonicalIdHooks(CanonicalIdHooks):
    """Explicit provider-local source-ID mappings with no fuzzy guessing."""

    competition_ids: Mapping[str, CompetitionId] = field(default_factory=dict)
    event_ids: Mapping[str, EventId] = field(default_factory=dict)
    market_ids: Mapping[str, MarketId] = field(default_factory=dict)
    selection_ids: Mapping[tuple[str, str], SelectionId] = field(default_factory=dict)

    def __post_init__(self) -> None:
        competitions = dict(self.competition_ids)
        events = dict(self.event_ids)
        markets = dict(self.market_ids)
        selections = dict(self.selection_ids)

        self._validate_text_mapping(competitions, CompetitionId, "competition_ids")
        self._validate_text_mapping(events, EventId, "event_ids")
        self._validate_text_mapping(markets, MarketId, "market_ids")
        for key, value in selections.items():
            if (
                not isinstance(key, tuple)
                or len(key) != 2
                or any(not isinstance(part, str) or not part.strip() for part in key)
            ):
                raise ValueError("selection_ids keys must be (market_id, selection_id) text tuples")
            if not isinstance(value, SelectionId):
                raise ValueError("selection_ids values must be SelectionId")

        object.__setattr__(self, "competition_ids", MappingProxyType(competitions))
        object.__setattr__(self, "event_ids", MappingProxyType(events))
        object.__setattr__(self, "market_ids", MappingProxyType(markets))
        object.__setattr__(self, "selection_ids", MappingProxyType(selections))

    @staticmethod
    def _validate_text_mapping(
        values: Mapping[str, object],
        expected_type: type[object],
        field_name: str,
    ) -> None:
        for key, value in values.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{field_name} keys must be non-empty text")
            if not isinstance(value, expected_type):
                raise ValueError(f"{field_name} contains an invalid canonical ID")

    def competition_id(self, record: SourceCompetition) -> CompetitionId | None:
        return self.competition_ids.get(record.external_id)

    def event_id(self, record: SourceEvent) -> EventId | None:
        return self.event_ids.get(record.external_id)

    def market_id(self, record: SourceMarket) -> MarketId | None:
        return self.market_ids.get(record.external_market_id)

    def selection_id(
        self,
        market: SourceMarket,
        record: SourceSelectionQuote,
    ) -> SelectionId | None:
        return self.selection_ids.get((market.external_market_id, record.external_selection_id))
